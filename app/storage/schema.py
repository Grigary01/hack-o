"""Версионирование SQLite. Проверка старой схемы выполняется до stamp/DDL."""
from functools import lru_cache
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from app.core.config import ROOT

MIGRATIONS = ROOT / 'migrations'
HEAD_REVISION = '0003_question_lifecycle'


class SchemaUpgradeRequired(RuntimeError):
    pass


def migration_config(connection):
    config = Config()
    config.set_main_option('script_location', str(MIGRATIONS))
    config.attributes['connection'] = connection
    return config


def schema_signature(connection):
    inspector = inspect(connection)
    result = {}
    for name in sorted(set(inspector.get_table_names()) - {'alembic_version'}):
        result[name] = {
            'columns': sorted((c['name'], str(c['type']), c['nullable']) for c in inspector.get_columns(name)),
            'pk': inspector.get_pk_constraint(name)['constrained_columns'],
            'fk': sorted((tuple(f['constrained_columns']), f['referred_table'], tuple(f['referred_columns']))
                         for f in inspector.get_foreign_keys(name)),
            'unique': sorted(tuple(c['column_names']) for c in inspector.get_unique_constraints(name)),
            'indexes': sorted((i['name'], tuple(i['column_names']), bool(i['unique']))
                              for i in inspector.get_indexes(name)),
        }
    return result


@lru_cache(maxsize=1)
def legacy_signature():
    expected = create_engine('sqlite://')
    try:
        with expected.connect() as connection:
            connection.connection.driver_connection.executescript(
                (MIGRATIONS / 'legacy_schema.sql').read_text())
            return schema_signature(connection)
    finally:
        expected.dispose()


@lru_cache(maxsize=None)
def revision_signature(revision):
    # Также распознаём точную известную схему без version table, созданную
    # переходной версией create_all(). Не доверяем текущим ORM-моделям.
    expected = create_engine('sqlite://')
    try:
        with expected.begin() as connection:
            command.upgrade(migration_config(connection), revision)
            return schema_signature(connection)
    finally:
        expected.dispose()


def upgrade_database(engine):
    # В SQLite Python по умолчанию DDL может исполняться вне транзакции.
    # Явный BEGIN также сериализует два одновременных запуска миграции.
    with engine.begin() as connection:
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        tables = set(inspect(connection).get_table_names())
        revision = MigrationContext.configure(connection).get_current_revision()
        config = migration_config(connection)
        if revision is None and tables - {'alembic_version'}:
            actual = schema_signature(connection)
            if actual == legacy_signature():
                command.stamp(config, '0001_baseline')
            elif actual == revision_signature('0002_conflict_resolutions'):
                command.stamp(config, '0002_conflict_resolutions')
            elif actual == revision_signature(HEAD_REVISION):
                command.stamp(config, HEAD_REVISION)
            else:
                raise SchemaUpgradeRequired('Неизвестная схема SQLite: обновление остановлено без изменения данных')
        elif revision == '0001_baseline' and schema_signature(connection) != legacy_signature():
            raise SchemaUpgradeRequired('Схема не соответствует 0001_baseline; обновление остановлено')
        elif revision == '0002_conflict_resolutions' and schema_signature(connection) != revision_signature(revision):
            raise SchemaUpgradeRequired('Схема не соответствует 0002_conflict_resolutions; обновление остановлено')
        command.upgrade(config, 'head')
        return MigrationContext.configure(connection).get_current_revision()


def ensure_schema(engine):
    with engine.connect() as connection:
        tables = inspect(connection).get_table_names()
        revision = MigrationContext.configure(connection).get_current_revision()
    if not tables:
        upgrade_database(engine)
    elif revision != HEAD_REVISION:
        raise SchemaUpgradeRequired('Сначала остановите приложение и выполните python -m scripts.migrate_db')
