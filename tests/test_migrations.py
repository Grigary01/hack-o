import sqlite3
import hashlib
from pathlib import Path

import pytest
from sqlalchemy import inspect, MetaData
from alembic import command, op

from app.storage import schema
from app.storage.db import create_db, open_engine
from app.storage.models import Base
from app.storage.schema import HEAD_REVISION, MIGRATIONS, SchemaUpgradeRequired, upgrade_database
from scripts.migrate_db import migrate
from scripts.seed_demo import seed


def legacy_database(path, observation):
    engine = open_engine('sqlite:///' + str(path))
    with engine.connect() as connection:
        connection.connection.driver_connection.executescript((MIGRATIONS / 'legacy_schema.sql').read_text())
    seed(engine)
    # Исторические данные создаём через отражённую старую схему: актуальная
    # бизнес-логика уже требует колонок следующих миграций.
    metadata = MetaData()
    metadata.reflect(bind=engine)
    import json
    with engine.begin() as connection:
        hotel_id = connection.execute(metadata.tables['hotels'].select()).first().id
        qid = hashlib.sha256(f'{hotel_id}|sea_view'.encode()).hexdigest()[:24]
        facts = [observation(hotel_id, 'sea_view', value, room='301', source='hotelier_simulated')
                 for value in (True, False)]
        created_at = facts[0].collected_at.isoformat()
        connection.execute(metadata.tables['hotelier_questions'].insert(), dict(id=qid,
            hotel_id=hotel_id, feature_key='sea_view', text='Уточните вид в номере 301',
            status='open', created_at=created_at))
        connection.execute(metadata.tables['hotelier_answers'].insert(), dict(id='legacy-answer',
            question_id=qid, text='В номере 301 есть вид на море.', extraction={
                'claims': [], 'unparsed': ['Исторический черновик'], 'parser_mode': 'bounded_rules'},
            status='pending', simulated=True, created_at=created_at))
        connection.execute(metadata.tables['rooms'].insert(), dict(id=hotel_id+':room:301',
            hotel_id=hotel_id, number='301', floor=3))
        for fact in facts:
            source = fact.evidence.source.model_dump(mode='json')
            source_id = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
            if connection.execute(metadata.tables['sources'].select().where(
                    metadata.tables['sources'].c.id == source_id)).first() is None:
                connection.execute(metadata.tables['sources'].insert(), dict(id=source_id, payload=source))
            connection.execute(metadata.tables['observations'].insert(), dict(id=fact.id,
                hotel_id=hotel_id, subject_id=fact.subject_id, feature_key=fact.feature_key,
                payload=fact.model_dump(mode='json')))
            connection.execute(metadata.tables['evidence'].insert(), dict(observation_id=fact.id,
                source_id=source_id, payload=fact.evidence.model_dump(mode='json')))
        ids = sorted(f.id for f in facts)
        connection.execute(metadata.tables['conflicts'].insert(), dict(
            id=hashlib.sha256('|'.join(ids).encode()).hexdigest(), hotel_id=hotel_id,
            subject_id=facts[0].subject_id, feature_key='sea_view', left_id=ids[0], right_id=ids[1],
            created_at=created_at, policy='withhold_and_ask_hotelier'))
    return engine


def snapshot(path):
    with sqlite3.connect(path) as db:
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='alembic_version'").fetchall()
        return {name: sorted(db.execute('SELECT '+(
            'id, hotel_id, feature_key, text, status, created_at' if name == 'hotelier_questions' else '*'
        )+' FROM "'+name+'"').fetchall(), key=repr) for (name,) in tables}


def test_clean_database_matches_current_models_and_is_repeatable(tmp_path):
    path = tmp_path / 'clean.db'
    result = migrate('sqlite:///' + str(path))
    assert result == {'revision': HEAD_REVISION, 'backup': None}
    assert migrate('sqlite:///' + str(path))['revision'] == HEAD_REVISION
    engine = create_db('sqlite:///' + str(path))
    expected = open_engine('sqlite://')
    try:
        Base.metadata.create_all(expected)
        with engine.connect() as actual, expected.connect() as reference:
            assert schema.schema_signature(actual) == schema.schema_signature(reference)
    finally:
        engine.dispose()
        expected.dispose()


def test_populated_legacy_upgrade_preserves_history_and_verified_backup(tmp_path, observation):
    path = tmp_path / 'legacy.db'
    engine = legacy_database(path, observation)
    engine.dispose()
    before = snapshot(path)
    with pytest.raises(SchemaUpgradeRequired, match='migrate_db'):
        create_db('sqlite:///' + str(path))
    result = migrate('sqlite:///' + str(path))
    assert result['revision'] == HEAD_REVISION
    assert snapshot(Path(result['backup'])) == before
    after = snapshot(path)
    assert after.pop('conflict_resolutions') == []
    assert after == before
    migrate('sqlite:///' + str(path))
    assert snapshot(path) == before | {'conflict_resolutions': []}


def test_unrecognized_legacy_schema_is_not_stamped_or_changed(tmp_path, observation):
    path = tmp_path / 'unknown.db'
    engine = legacy_database(path, observation)
    with engine.begin() as connection:
        connection.exec_driver_sql('ALTER TABLE rooms ADD COLUMN unexpected TEXT')
    before = snapshot(path)
    with pytest.raises(SchemaUpgradeRequired, match='Неизвестная схема'):
        upgrade_database(engine)
    assert snapshot(path) == before
    assert 'alembic_version' not in inspect(engine).get_table_names()
    engine.dispose()


def test_failure_rolls_back_stamp_and_ddl(tmp_path, observation, monkeypatch):
    path = tmp_path / 'rollback.db'
    engine = legacy_database(path, observation)
    before = snapshot(path)
    def interrupted(config, target):
        config.attributes['connection'].exec_driver_sql('CREATE TABLE should_rollback (id INTEGER)')
        raise RuntimeError('Прерванная миграция')
    monkeypatch.setattr(schema.command, 'upgrade', interrupted)
    with pytest.raises(RuntimeError, match='Прерванная миграция'):
        upgrade_database(engine)
    assert snapshot(path) == before
    assert 'alembic_version' not in inspect(engine).get_table_names()
    engine.dispose()


def test_exact_unversioned_current_schema_can_be_adopted(tmp_path):
    engine = open_engine('sqlite:///' + str(tmp_path / 'transitional.db'))
    Base.metadata.create_all(engine)
    assert upgrade_database(engine) == HEAD_REVISION
    engine.dispose()


def stage2_database(path, observation):
    engine = legacy_database(path, observation)
    with engine.begin() as connection:
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        config = schema.migration_config(connection)
        command.stamp(config, '0001_baseline')
        command.upgrade(config, '0002_conflict_resolutions')
        conflict = connection.exec_driver_sql('SELECT id, left_id, created_at FROM conflicts').first()
        connection.exec_driver_sql('INSERT INTO conflict_resolutions VALUES (?, ?, ?, ?, ?)',
            (conflict.id, conflict.left_id, 'Историческое решение', conflict.created_at, 'demo_operator'))
    return engine


def test_stage2_upgrade_keeps_decisions_and_backfills_question_review(tmp_path, observation):
    path = tmp_path / 'stage2.db'
    engine = stage2_database(path, observation)
    before = snapshot(path)
    engine.dispose()
    result = migrate('sqlite:///' + str(path))
    assert result['revision'] == HEAD_REVISION
    assert snapshot(path) == before == snapshot(Path(result['backup']))
    import json
    with sqlite3.connect(path) as db:
        context, updated_at, created_at = db.execute(
            'SELECT context, updated_at, created_at FROM hotelier_questions').fetchone()
    assert json.loads(context)['review_answer_id'] == 'legacy-answer'
    assert updated_at == created_at


def test_question_column_changes_roll_back_if_migration_fails(tmp_path, observation, monkeypatch):
    engine = stage2_database(tmp_path / 'stage3_rollback.db', observation)
    with engine.connect() as connection:
        before = schema.schema_signature(connection)
    original = op.add_column
    def interrupted(table, column, **kwargs):
        if column.name == 'updated_at':
            raise RuntimeError('Ошибка после первой новой колонки')
        return original(table, column, **kwargs)
    # Замораживаем ожидаемую v2-схему до подмены выполнения миграции.
    schema.revision_signature('0002_conflict_resolutions')
    monkeypatch.setattr(op, 'add_column', interrupted)
    with pytest.raises(RuntimeError, match='Ошибка после первой'):
        upgrade_database(engine)
    with engine.connect() as connection:
        assert schema.schema_signature(connection) == before
        assert connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == '0002_conflict_resolutions'
    engine.dispose()
