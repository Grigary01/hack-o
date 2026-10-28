from datetime import timedelta

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.agent.feature_agent import FeatureAgent
from app.hotelier.dialogue import ask_hotelier, submit_answer, confirm_answer
from app.schemas.hotelier import HotelierQuestion
from app.storage.models import QuestionRow, AnswerRow, ObservationRow
from app.storage.repository import Repository, now_utc


def confirmed(repo, question, text):
    answer = submit_answer(repo, question['id'], text)
    return confirm_answer(repo, answer['id'], True)


def test_complete_answer_closes_question_without_changing_identity_and_repeated_search_does_not_reopen(repo):
    hotel = repo.hotels()[0]
    q = ask_hotelier(repo, hotel.id, 'sea_view')
    confirmed(repo, q, 'В номере 301 есть вид на море.')
    row = repo.question(q['id'])
    assert row.status == 'answered' and row.context['reasons'] == []
    updated = row.updated_at
    for simulated in (False, True, False):
        FeatureAgent(repo).ensure(hotel.id, 'sea_view', simulated)
    repeated = ask_hotelier(repo, hotel.id, 'sea_view')
    assert repeated['id'] == q['id'] and repeated['created_at'] == q['created_at']
    assert repeated['status'] == 'answered' and repeated['updated_at'] == updated
    assert len(repo.questions()) == 1


def test_new_conflict_reopens_same_question_and_resolution_closes_it(repo):
    hotel = repo.hotels()[0]
    q = ask_hotelier(repo, hotel.id, 'sea_view')
    first = confirmed(repo, q, 'В номере 301 есть вид на море.')
    confirmed(repo, q, 'В номере 301 нет вида на море.')
    row = repo.question(q['id'])
    assert row.status == 'open' and row.context['reasons'] == ['conflicted']
    assert row.context['subject_ids'] == [hotel.id + ':room:301']
    conflict = repo.conflict_records(hotel.id)[0]
    repo.resolve_conflict(conflict.id, first['observation_ids'][0], 'Уточнение завершено')
    assert row.status == 'answered' and not row.context['subject_ids']
    confirmed(repo, q, 'В номере 301 нет вида на море.')
    assert row.status == 'open'
    assert len(repo.questions()) == 1
    assert repo.session.scalar(select(func.count()).select_from(AnswerRow)) == 3


def test_answer_for_one_room_does_not_close_other_room_conflict(repo):
    hotel = repo.hotels()[0]
    q = ask_hotelier(repo, hotel.id, 'sea_view')
    confirmed(repo, q, 'В номерах 301–302 есть вид на море.')
    confirmed(repo, q, 'В номере 302 нет вида на море.')
    confirmed(repo, q, 'В номере 301 есть вид на море.')
    row = repo.question(q['id'])
    assert row.status == 'open' and row.context['subject_ids'] == [hotel.id + ':room:302']


def test_pending_unparsed_and_rejected_replies_do_not_close_clarification(repo):
    hotel = repo.hotels()[0]
    q = ask_hotelier(repo, hotel.id, 'sea_view')
    confirmed(repo, q, 'В номере 301 есть вид на море.')
    draft = submit_answer(repo, q['id'], 'Возможно, в номере 301 вид на море только зимой.')
    row = repo.question(q['id'])
    assert row.status == 'open'
    assert row.context['reasons'] == ['pending_answer', 'unparsed_answer']
    with pytest.raises(ValueError, match='не полностью'):
        confirm_answer(repo, draft['id'], True)
    confirm_answer(repo, draft['id'], False)
    assert row.status == 'open' and row.context['reasons'] == ['rejected_answer']
    confirmed(repo, q, 'В номере 301 есть вид на море.')
    assert row.status == 'answered'


def test_latest_submitted_answer_is_explicit_even_if_dates_match_and_older_draft_is_processed(repo):
    hotel = repo.hotels()[0]
    q = ask_hotelier(repo, hotel.id, 'sea_view')
    older = submit_answer(repo, q['id'], 'В номере 301 есть вид на море.')
    latest = submit_answer(repo, q['id'], 'Возможно, в номере 301 вид на море.')
    confirm_answer(repo, older['id'], True)
    row = repo.question(q['id'])
    assert row.status == 'open' and row.context['review_answer_id'] == latest['id']
    assert 'unparsed_answer' in row.context['reasons']
    newer = submit_answer(repo, q['id'], 'В номере 301 есть вид на море.')
    confirm_answer(repo, newer['id'], True)
    confirm_answer(repo, latest['id'], False)
    assert row.status == 'answered' and row.context['review_answer_id'] == newer['id']


def test_unknown_room_from_pending_answer_stays_targeted_until_confirmed(repo):
    hotel = repo.hotels()[0]
    q = ask_hotelier(repo, hotel.id, 'sea_view')
    submit_answer(repo, q['id'], 'В номере 302 есть вид на море.')
    confirmed(repo, q, 'В номере 301 есть вид на море.')
    row = repo.question(q['id'])
    assert row.status == 'open' and row.context['subject_ids'] == [hotel.id + ':room:302']
    assert row.context['reasons'] == ['unknown']
    confirmed(repo, q, 'В номере 302 есть вид на море.')
    assert row.status == 'answered'


def test_ttl_reopens_answered_question_before_status_filter_and_preserves_dates(repo, monkeypatch):
    hotel = repo.hotels()[0]
    q = ask_hotelier(repo, hotel.id, 'sea_view')
    confirmed(repo, q, 'В номере 301 есть вид на море.')
    original = repo.observations(hotel.id, 'sea_view')[0]
    future = now_utc() + timedelta(days=91)
    monkeypatch.setattr('app.storage.repository.now_utc', lambda: future)
    questions = repo.questions(hotel_id=hotel.id, status='open')
    assert len(questions) == 1
    current = questions[0]
    assert current['id'] == q['id'] and current['created_at'] == q['created_at']
    assert current['context']['reasons'] == ['stale']
    assert current['updated_at'] == future.isoformat()
    repeated = repo.questions(hotel_id=hotel.id, status='open')[0]
    assert repeated == current
    saved = repo.observations(hotel.id, 'sea_view')[0]
    assert saved.expires_at == original.expires_at and saved.observed_at == original.observed_at


def test_resolved_but_expired_fact_does_not_close_question(repo, observation):
    hotel = repo.hotels()[0]
    q = ask_hotelier(repo, hotel.id, 'sea_view')
    facts = [observation(hotel.id, 'sea_view', v, room='301', offset=-30, source='hotelier_simulated')
             for v in (True, False)]
    for fact in facts:
        repo.save_observation(fact)
    repo.resolve_conflict(repo.conflict_records()[0].id, facts[0].id, 'Старое свидетельство')
    row = repo.question(q['id'])
    assert row.status == 'open' and row.context['reasons'] == ['stale']


def test_expired_geo_observation_requests_snapshot_refresh_without_hotelier_question(repo, monkeypatch):
    hotel = repo.hotels()[0]
    future = now_utc() + timedelta(days=91)
    monkeypatch.setattr('app.features.service.now_utc', lambda: future)
    monkeypatch.setattr('app.storage.repository.now_utc', lambda: future)
    decision = FeatureAgent(repo).ensure(hotel.id, 'walking_distance_to_beach_m')
    assert decision['action'] == 'request_snapshot_refresh'
    assert repo.questions() == []


def test_api_filters_and_existing_frontend_fields(client):
    hotels = client.get('/api/hotels').json()
    for hotel in hotels[:2]:
        r = client.post('/api/hotelier/questions', json={'hotel_id': hotel['id'], 'feature_key': 'sea_view'})
        assert r.status_code == 200
        question = HotelierQuestion.model_validate(r.json())
        assert question.status == 'open' and question.context.reasons == ['unknown']
    filtered = client.get('/api/hotelier/questions', params={'hotel_id': hotels[0]['id'], 'status': 'open'})
    assert filtered.status_code == 200 and len(filtered.json()) == 1
    assert {'id', 'hotel_id', 'feature_key', 'text', 'status', 'created_at'} <= filtered.json()[0].keys()
    assert client.get('/api/hotelier/questions', params={'status': 'invalid'}).status_code == 422
    assert client.get('/api/hotelier/questions', params={'hotel_id': 'missing'}).status_code == 404
    assert client.get('/api/hotelier/questions', params={'status': 'answered'}).json() == []


def test_search_does_not_list_answered_question_as_pending(client):
    hotel = client.get('/api/hotels').json()[0]
    q = client.post('/api/hotelier/questions', json={'hotel_id': hotel['id'], 'feature_key': 'sea_view'}).json()
    a = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': 'В номере 301 есть вид на море.'}).json()
    client.post(f'/api/hotelier/answers/{a["id"]}/confirm', json={'accept': True})
    result = client.post('/api/search', json={'text': 'Нужен номер обязательно с видом на море'}).json()
    row = next(r for r in result['needs_verification'] if r['hotel']['id'] == hotel['id'])
    assert q['id'] not in row['pending_hotelier_question_ids']
    assert client.get('/api/hotelier/questions', params={'hotel_id': hotel['id'], 'status': 'answered'}).json()


def test_failure_during_confirmation_does_not_partially_close_question(client, engine, monkeypatch):
    hotel = client.get('/api/hotels').json()[0]
    q = client.post('/api/hotelier/questions', json={'hotel_id': hotel['id'], 'feature_key': 'sea_view'}).json()
    a = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': 'В номере 301 есть вид на море.'}).json()
    original = Repository.save_observation
    def interrupted(self, fact):
        original(self, fact)
        raise ValueError('Ошибка после записи факта')
    monkeypatch.setattr(Repository, 'save_observation', interrupted)
    assert client.post(f'/api/hotelier/answers/{a["id"]}/confirm', json={'accept': True}).status_code == 422
    with Session(engine) as session:
        assert session.get(QuestionRow, q['id']).status == 'open'
        assert session.get(AnswerRow, a['id']).status == 'pending'
        assert session.scalar(select(func.count()).select_from(ObservationRow).where(
            ObservationRow.feature_key == 'sea_view')) == 0
