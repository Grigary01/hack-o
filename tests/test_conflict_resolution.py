from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.agent.feature_agent import FeatureAgent
from app.core.config import settings
from app.features.service import resolve_feature
from app.main import create_app
from app.ml.query_parser import FixtureQueryParser
from app.ml.ranking import rank_hotels
from app.schemas.query import ParsedHotelQuery, HardConstraint
from app.storage.db import create_db
from app.storage.models import ConflictResolutionRow
from app.storage.repository import Repository, now_utc
from scripts.seed_demo import seed


def pair(repo, observation, *, simulated=True):
    hotel = repo.hotels()[0]
    source = 'hotelier_simulated' if simulated else 'hotelier'
    a = observation(hotel.id, 'sea_view', True, room='301', source=source)
    b = observation(hotel.id, 'sea_view', False, room='301', source=source)
    repo.save_observation(a)
    repo.save_observation(b)
    return hotel, a, b, repo.conflict_records(hotel.id)[0]


def state(repo, fact, **kwargs):
    return resolve_feature(repo.observations(fact.hotel_id), fact.subject_id,
        fact.feature_key, True, conflicts=repo.conflict_records(fact.hotel_id), **kwargs)


def test_selected_value_used_by_resolver_agent_and_ml_without_database_dependency(repo, observation):
    hotel, a, b, conflict = pair(repo, observation)
    assert state(repo, a).status == 'conflicted'
    repo.resolve_conflict(conflict.id, a.id, 'Проверен исходный ответ')
    current = state(repo, a)
    assert current.value is True and current.status == a.status
    assert current.resolved_conflict_ids == [conflict.id]
    assert {o.id for o in current.observations} == {a.id, b.id}
    assert current.observations[0].expires_at == a.expires_at
    assert FeatureAgent(repo).ensure(hotel.id, 'sea_view', True)['action'] == 'read_evidence'
    query = ParsedHotelQuery(hard_constraints=[HardConstraint(
        feature_key='sea_view', operator='=', value=True, scope='room')])
    rows = [(hotel, [a, b])]
    # Старый вызов остаётся допустимым, но без контекста не обходит конфликт.
    assert not rank_hotels(query, rows, True)['matched']
    assert rank_hotels(query, rows, True, conflicts=repo.conflict_records())['matched']
    assert not rank_hotels(query, rows, False, conflicts=repo.conflict_records())['matched']


def test_new_contradiction_requires_another_explicit_decision(repo, observation):
    hotel, a, b, first = pair(repo, observation)
    repo.resolve_conflict(first.id, a.id, 'Первое решение')
    c = observation(hotel.id, 'sea_view', False, room='301', source='hotelier_simulated')
    repo.save_observation(c)
    assert state(repo, a).value is None and state(repo, a).status == 'conflicted'
    second = next(c for c in repo.conflict_records() if c.id != first.id)
    repo.resolve_conflict(second.id, a.id, 'Новый ответ тоже проверен')
    assert state(repo, a).value is True


def test_one_resolved_pair_cannot_hide_another_and_inconsistent_decisions_block(repo, observation):
    hotel, a, b, first = pair(repo, observation)
    c = observation(hotel.id, 'sea_view', True, room='301', source='hotelier_simulated')
    repo.save_observation(c)
    second = next(c for c in repo.conflict_records() if c.id != first.id)
    repo.resolve_conflict(first.id, a.id, 'Выбран первый положительный ответ')
    assert state(repo, a).status == 'conflicted'
    repo.resolve_conflict(second.id, b.id, 'Несогласованное решение')
    assert state(repo, a).status == 'conflicted'


def test_expired_selection_does_not_resurrect_the_rejected_observation(repo, observation):
    hotel = repo.hotels()[0]
    a = observation(hotel.id, 'sea_view', True, room='301', offset=-9, source='hotelier_simulated')
    b = observation(hotel.id, 'sea_view', False, room='301', source='hotelier_simulated')
    repo.save_observation(a)
    repo.save_observation(b)
    repo.resolve_conflict(repo.conflict_records()[0].id, a.id, 'Выбран факт с исходным TTL')
    assert state(repo, a).value is True
    expired = state(repo, a, now=now_utc() + timedelta(days=2))
    assert expired.value is None and expired.status == 'stale'


def test_real_resolution_never_turns_simulation_into_a_real_fact(repo, observation):
    hotel, a, b, conflict = pair(repo, observation)
    repo.resolve_conflict(conflict.id, a.id, 'Демо')
    real = resolve_feature([a, b], a.subject_id, 'sea_view', conflicts=repo.conflict_records())
    assert real.value is None and real.status == 'unknown'
    assert not real.resolved_conflict_ids


def test_real_false_value_and_original_confidence_are_preserved(repo, observation):
    hotel, a, b, conflict = pair(repo, observation, simulated=False)
    repo.resolve_conflict(conflict.id, b.id, 'Проверено отсутствие вида')
    current = resolve_feature([a, b], a.subject_id, 'sea_view', conflicts=repo.conflict_records())
    assert current.value is False and current.status == b.status
    original = next(o for o in current.observations if o.id == b.id)
    assert original.confidence_level == b.confidence_level
    assert original.evidence.source == b.evidence.source
    assert original.observed_at == b.observed_at and original.expires_at == b.expires_at


def test_future_decision_and_wrong_subject_context_are_not_applied(repo, observation):
    hotel, a, b, conflict = pair(repo, observation)
    resolution, _ = repo.resolve_conflict(conflict.id, a.id, 'Демо')
    future = conflict.model_copy(update={'resolution': resolution.model_copy(
        update={'resolved_at': now_utc() + timedelta(days=1)})})
    wrong = conflict.model_copy(update={'resolution': resolution, 'hotel_id': 'other-hotel'})
    for invalid in (future, wrong):
        assert resolve_feature([a, b], a.subject_id, 'sea_view', True,
                               conflicts=[invalid]).status == 'conflicted'


def api_pair(client):
    hotel = client.get('/api/hotels').json()[0]
    question = client.post('/api/hotelier/questions', json={
        'hotel_id': hotel['id'], 'feature_key': 'sea_view'}).json()
    answers = []
    for text in ('В номере 301 есть вид на море.', 'В номере 301 нет вида на море.'):
        answer = client.post(f'/api/hotelier/questions/{question["id"]}/answer', json={'text': text}).json()
        confirmed = client.post(f'/api/hotelier/answers/{answer["id"]}/confirm', json={'accept': True})
        assert confirmed.status_code == 200
        answers.append(confirmed.json()['observation_ids'][0])
    conflict = client.get('/api/hotelier/conflicts', params={'hotel_id': hotel['id'], 'status': 'open'}).json()[0]
    return hotel, conflict, answers


def test_api_resolve_search_evidence_idempotency_and_compatibility(client, engine):
    hotel, conflict, answers = api_pair(client)
    path = f'/api/hotelier/conflicts/{conflict["id"]}/resolve'
    payload = {'selected_observation_id': answers[0], 'reason': '  Проверка номера 301  '}
    response = client.post(path, json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body['current']['value'] is True and body['current']['status'] == 'estimated'
    assert body['resolution']['reason'] == 'Проверка номера 301'
    assert body['resolution']['operator_id'] == 'demo_operator'
    assert not body['idempotent']
    again = client.post(path, json=payload).json()
    assert again['idempotent'] and again['resolution'] == body['resolution']
    for change in ({'selected_observation_id': answers[1]}, {'reason': 'Другая причина'}):
        assert client.post(path, json=payload | change).status_code == 409
    assert not client.get('/api/hotelier/conflicts', params={'status': 'open'}).json()
    assert len(client.get('/api/hotelier/conflicts', params={'status': 'resolved'}).json()) == 1
    assert client.get('/api/hotelier/conflicts', params={'status': 'invalid'}).status_code == 422
    evidence = client.get(f'/api/hotels/{hotel["id"]}/evidence').json()
    demo = next(x for x in evidence['current_demo'] if x['feature_key'] == 'sea_view')
    real = next(x for x in evidence['current_real'] if x['feature_key'] == 'sea_view')
    assert demo['value'] is True and real['value'] is None
    assert demo['resolved_conflict_ids'] == [conflict['id']]
    strict = {'text': 'Нужен номер обязательно с видом на море', 'ranking_method': 'balanced_v2', 'balance': .4}
    assert not client.post('/api/search', json=strict).json()['matched']
    for method in ('balanced_v2', 'weighted_v1'):
        result = client.post('/api/search', json=strict | {'include_simulated': True, 'ranking_method': method}).json()
        assert [r['hotel']['id'] for r in result['matched']] == [hotel['id']]
        decision = next(t for t in result['trace'] if t['hotel_id'] == hotel['id'])
        assert decision['action'] == 'read_evidence'
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ConflictResolutionRow)) == 1


def test_invalid_selection_reason_and_demo_guard(client, engine):
    hotel, conflict, answers = api_pair(client)
    path = f'/api/hotelier/conflicts/{conflict["id"]}/resolve'
    evidence = client.get(f'/api/hotels/{hotel["id"]}/evidence').json()
    foreign = next(o['id'] for o in evidence['observations'] if o['feature_key'] != 'sea_view')
    assert client.post(path, json={'selected_observation_id': foreign, 'reason': 'Чужое свидетельство'}).status_code == 422
    assert client.post(path, json={'selected_observation_id': 'missing', 'reason': 'Проверка'}).status_code == 404
    for reason in ('', '   ', 'x' * 2001):
        assert client.post(path, json={'selected_observation_id': answers[0], 'reason': reason}).status_code == 422
    assert client.post(path, json={'selected_observation_id': answers[0], 'reason': 'Проверка', 'operator_id': 'fake'}).status_code == 422
    assert client.post('/api/hotelier/conflicts/missing/resolve', json={
        'selected_observation_id': answers[0], 'reason': 'Проверка'}).status_code == 404
    with TestClient(create_app(engine=engine, parser=FixtureQueryParser(), config=replace(settings, demo_mode=False))) as guarded:
        assert guarded.get('/api/hotelier/conflicts').status_code == 403
        assert guarded.post(path, json={'selected_observation_id': answers[0], 'reason': 'Демо'}).status_code == 403


def test_error_after_insert_rolls_back_whole_resolution(client, engine, monkeypatch):
    hotel, conflict, answers = api_pair(client)
    original = Repository.resolve_conflict
    def fail_after_insert(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise ValueError('Ошибка после записи')
    with monkeypatch.context() as scoped:
        scoped.setattr(Repository, 'resolve_conflict', fail_after_insert)
        response = client.post(f'/api/hotelier/conflicts/{conflict["id"]}/resolve', json={
            'selected_observation_id': answers[0], 'reason': 'Не должна сохраниться'})
        assert response.status_code == 422
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ConflictResolutionRow)) == 0
    assert client.get('/api/hotelier/conflicts').json()[0]['status'] == 'open'


def test_concurrent_identical_requests_create_one_decision(tmp_path, observation):
    engine = create_db('sqlite:///' + str(tmp_path / 'concurrent.db'))
    try:
        seed(engine)
        with Session(engine) as session, session.begin():
            repo = Repository(session)
            _, a, _, conflict = pair(repo, observation)
        def resolve():
            with Session(engine) as session, session.begin():
                return Repository(session).resolve_conflict(conflict.id, a.id, 'Одинаковый запрос')[1]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: resolve(), range(2)))
        assert sorted(results) == [False, True]
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(ConflictResolutionRow)) == 1
    finally:
        engine.dispose()
