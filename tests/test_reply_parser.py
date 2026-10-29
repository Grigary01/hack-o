from copy import deepcopy
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ReplyParserUnavailable
from app.hotelier.reply_parser import FixtureReplyParser, make_reply_parser
from app.main import create_app
from app.ml.query_parser import FixtureQueryParser
from app.schemas.hotelier import ReplyExtraction
from app.storage.models import AnswerRow, ObservationRow, RoomRow

TEXT = 'В номере 301 есть вид на море.'
VALID = {'claims': [{'room_number': '301', 'floor': None, 'feature_key': 'sea_view',
                     'value': True, 'quote': 'В номере 301 есть вид на море'}], 'unparsed': []}


class StubMLReplyParser:
    mode = 'stub_ml'

    def __init__(self, result=None, error=None):
        self.result = deepcopy(VALID) if result is None else result
        self.error = error
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return deepcopy(self.result)


def question(client):
    hotel = client.get('/api/hotels').json()[0]
    response = client.post('/api/hotelier/questions', json={'hotel_id': hotel['id'], 'feature_key': 'sea_view'})
    assert response.status_code == 200
    return response.json()


def app_client(engine, parser):
    return TestClient(create_app(engine=engine, parser=FixtureQueryParser(), reply_parser=parser))


def counts(engine):
    with Session(engine) as session:
        return tuple(session.scalar(select(func.count()).select_from(model))
                     for model in (AnswerRow, ObservationRow, RoomRow))


def test_injected_ml_only_receives_feature_and_text_and_confirmation_is_still_required(engine):
    parser = StubMLReplyParser(ReplyExtraction.model_validate(VALID))
    with app_client(engine, parser) as client:
        q = question(client)
        before = counts(engine)
        response = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': TEXT})
        assert response.status_code == 200
        answer = response.json()
        assert parser.calls == [{'feature_key': 'sea_view', 'text': TEXT}]
        assert answer['question_id'] == q['id'] and answer['status'] == 'pending'
        assert answer['simulated'] is True and answer['text'] == TEXT
        assert answer['extraction']['parser_mode'] == 'stub_ml'
        assert counts(engine) == (before[0] + 1, before[1], before[2])
        result = client.post(f'/api/hotelier/answers/{answer["id"]}/confirm', json={'accept': True})
        assert result.status_code == 200
        evidence = client.get(f'/api/hotels/{q["hotel_id"]}/evidence').json()
        fact = next(o for o in evidence['observations'] if o['feature_key'] == 'sea_view')
        assert fact['evidence']['source']['type'] == 'hotelier_simulated'
        assert fact['evidence']['raw_excerpt'] == TEXT
        assert fact['evidence']['details']['quote'] == VALID['claims'][0]['quote']
        strict = {'text': 'Нужен номер обязательно с видом на море'}
        assert not client.post('/api/search', json=strict).json()['matched']
        assert [r['hotel']['id'] for r in client.post('/api/search', json=strict | {'include_simulated': True}).json()['matched']] == [q['hotel_id']]


@pytest.mark.parametrize(('field', 'value'), [
    ('feature_key', 'soundproofing'), ('feature_key', 'invented_feature'),
    ('room_number', 'all'), ('room_number', '999'), ('value', 'true'),
    ('value', 1), ('floor', True), ('floor', '3'), ('quote', ''),
    ('quote', 'Несуществующая цитата'), ('hotel_id', 'foreign-hotel'),
])
def test_invalid_or_ungrounded_claim_is_rejected_before_pending(engine, field, value):
    raw = deepcopy(VALID)
    raw['claims'][0][field] = value
    with app_client(engine, StubMLReplyParser(raw)) as client:
        q = question(client)
        before = counts(engine)
        response = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': TEXT})
        assert response.status_code == 502
        assert counts(engine) == before
        saved = client.get('/api/hotelier/questions', params={'hotel_id': q['hotel_id']}).json()[0]
        assert saved == q


def test_mutated_pydantic_instance_is_revalidated(engine):
    raw = ReplyExtraction.model_validate(VALID)
    raw.claims[0].value = 1
    with app_client(engine, StubMLReplyParser(raw)) as client:
        q = question(client)
        before = counts(engine)
        assert client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': TEXT}).status_code == 502
        assert counts(engine) == before


@pytest.mark.parametrize('text', [
    'В номере 301 вид на море только зимой.',
    'В номере 301 вид на море, если нет тумана.',
    'В номере 301 вид на море иногда.',
    'В номере 301, кажется, есть вид на море.',
])
def test_model_cannot_silently_turn_conditions_into_unconditional_facts(engine, text):
    raw = deepcopy(VALID)
    raw['claims'][0]['quote'] = text
    with app_client(engine, StubMLReplyParser(raw)) as client:
        q = question(client)
        response = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': text})
        assert response.status_code == 200
        answer = response.json()
        assert answer['extraction']['unparsed']
        before = counts(engine)
        assert client.post(f'/api/hotelier/answers/{answer["id"]}/confirm', json={'accept': True}).status_code == 422
        assert counts(engine) == before
        current = client.get('/api/hotelier/questions', params={'hotel_id': q['hotel_id']}).json()[0]
        assert current['status'] == 'open' and 'unparsed_answer' in current['context']['reasons']


def test_duplicate_claims_are_deduplicated_but_contradictions_require_review(engine):
    raw = deepcopy(VALID)
    raw['claims'] *= 2
    with app_client(engine, StubMLReplyParser(raw)) as client:
        q = question(client)
        answer = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': TEXT}).json()
        assert len(answer['extraction']['claims']) == 1
        result = client.post(f'/api/hotelier/answers/{answer["id"]}/confirm', json={'accept': True}).json()
        assert len(result['observation_ids']) == 1
    text = TEXT + ' В номере 301 нет вида на море.'
    raw = deepcopy(VALID)
    raw['claims'].append(raw['claims'][0] | {'value': False, 'quote': 'В номере 301 нет вида на море'})
    with app_client(engine, StubMLReplyParser(raw)) as client:
        q = question(client)
        answer = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': text}).json()
        assert answer['extraction']['unparsed']
        assert client.post(f'/api/hotelier/answers/{answer["id"]}/confirm', json={'accept': True}).status_code == 422


@pytest.mark.parametrize('error', [
    ReplyParserUnavailable('Сервис не настроен'), TimeoutError('private upstream detail'),
    httpx.ReadTimeout('private upstream detail'), OSError('private upstream detail'),
])
def test_model_failure_is_503_and_does_not_create_answer_or_fact(engine, error):
    with app_client(engine, StubMLReplyParser(error=error)) as client:
        q = question(client)
        before = counts(engine)
        response = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': TEXT})
        assert response.status_code == 503 and 'private upstream detail' not in response.text
        assert counts(engine) == before


def test_saved_extraction_is_checked_again_before_creating_facts(client, engine):
    q = question(client)
    answer = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': TEXT}).json()
    with Session(engine) as session, session.begin():
        row = session.get(AnswerRow, answer['id'])
        changed = deepcopy(row.extraction)
        changed['claims'][0]['feature_key'] = 'soundproofing'
        row.extraction = changed
    before = counts(engine)
    response = client.post(f'/api/hotelier/answers/{answer["id"]}/confirm', json={'accept': True})
    assert response.status_code == 422 and counts(engine) == before
    with Session(engine) as session:
        assert session.get(AnswerRow, answer['id']).status == 'pending'


def test_fixture_is_explicit_and_unknown_text_is_not_replaced_by_a_nearby_example(engine):
    config = replace(settings, reply_parser_mode='fixture')
    with TestClient(create_app(engine=engine, parser=FixtureQueryParser(), config=config)) as client:
        q = question(client)
        text = '301: море видно. 302: окна во двор.'
        answer = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': text}).json()
        assert answer['extraction']['parser_mode'] == 'fixture'
        assert [c['value'] for c in answer['extraction']['claims']] == [True, False]
        unknown = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': text.replace('301', '401')}).json()
        assert not unknown['extraction']['claims'] and unknown['extraction']['unparsed']
        assert client.get('/api/health').json()['reply_parser_mode'] == 'fixture'
    assert make_reply_parser(replace(settings, reply_parser_mode='rules')).mode == 'bounded_rules'
    assert isinstance(make_reply_parser(config), FixtureReplyParser)
    with pytest.raises(ValueError, match='REPLY_PARSER_MODE'):
        make_reply_parser(replace(settings, reply_parser_mode='unknown'))


def test_empty_result_requires_clarification_and_blank_input_does_not_call_ml(engine):
    parser = StubMLReplyParser({'claims': [], 'unparsed': []})
    with app_client(engine, parser) as client:
        q = question(client)
        assert client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': '   '}).status_code == 422
        assert not parser.calls
        answer = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': TEXT}).json()
        assert answer['extraction']['unparsed'] and not answer['extraction']['claims']
