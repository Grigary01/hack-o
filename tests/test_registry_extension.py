from dataclasses import replace
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.hotelier.reply_validation import parse_reply
from app.main import create_app
from app.ml.query_parser import FixtureQueryParser, OllamaQueryParser, GroqQueryParser
from app.ml.reply_parser import OllamaReplyParser, GroqReplyParser

KEY = 'blackout_curtains'
QUERY = 'Нужен номер с плотными шторами'
POSITIVE = 'В номере 501 есть плотные шторы.'
NEGATIVE = 'В номере 502 нет плотных штор.'


def reply(client, qid, text, accept=True):
    response = client.post(f'/api/hotelier/questions/{qid}/answer', json={'text': text})
    assert response.status_code == 200
    answer = response.json()
    if accept:
        response = client.post(f'/api/hotelier/answers/{answer["id"]}/confirm', json={'accept': True})
        assert response.status_code == 200
    return answer, response.json()


@pytest.mark.parametrize('reply_mode', ['rules', 'fixture'])
def test_registry_feature_runs_through_parse_question_confirmation_storage_and_search(engine, reply_mode):
    with TestClient(create_app(engine=engine, parser=FixtureQueryParser(),
            config=replace(settings, reply_parser_mode=reply_mode))) as client:
        definitions = client.get('/api/features').json()
        assert definitions[KEY]['provider'] == 'hotelier' and definitions[KEY]['scope'] == 'room'
        assert QUERY in client.get('/api/demo-queries').json()
        parsed = client.post('/api/parse-query', json={'text': QUERY}).json()
        assert parsed['hard_constraints'][0]['feature_key'] == KEY
        before = client.post('/api/search', json={'text': QUERY, 'include_simulated': True}).json()
        assert not before['matched']
        hotel = client.get('/api/hotels').json()[0]
        questions = client.get('/api/hotelier/questions', params={'hotel_id': hotel['id']}).json()
        q = next(q for q in questions if q['feature_key'] == KEY)
        pending, _ = reply(client, q['id'], POSITIVE, accept=False)
        assert pending['extraction']['claims'][0]['feature_key'] == KEY
        assert not client.post('/api/search', json={'text': QUERY, 'include_simulated': True}).json()['matched']
        confirmed = client.post(f'/api/hotelier/answers/{pending["id"]}/confirm', json={'accept': True})
        assert confirmed.status_code == 200
        negative, _ = reply(client, q['id'], NEGATIVE)
        assert negative['extraction']['claims'][0]['value'] is False
        for method in ('balanced_v2', 'weighted_v1'):
            result = client.post('/api/search', json={'text': QUERY, 'include_simulated': True,
                                                      'ranking_method': method}).json()
            assert [r['hotel']['id'] for r in result['matched']] == [hotel['id']]
            assert result['matched'][0]['recommended_room_id'] == hotel['id'] + ':room:501'
        assert not client.post('/api/search', json={'text': QUERY}).json()['matched']
        evidence = client.get(f'/api/hotels/{hotel["id"]}/evidence').json()
        facts = [o for o in evidence['observations'] if o['feature_key'] == KEY]
        assert {o['value'] for o in facts} == {True, False}
        from datetime import datetime, timedelta
        assert all(datetime.fromisoformat(o['expires_at']) - datetime.fromisoformat(o['observed_at'])
                   == timedelta(days=180) for o in facts)
        assert all(o['evidence']['source']['type'] == 'hotelier_simulated' and o['confidence_level'] == 'low'
                   for o in facts)


def test_new_feature_cannot_be_combined_with_sea_view_from_a_different_room(client):
    hotel = client.get('/api/hotels').json()[0]
    q = client.post('/api/hotelier/questions', json={'hotel_id': hotel['id'], 'feature_key': KEY}).json()
    reply(client, q['id'], POSITIVE)
    view = client.post('/api/hotelier/questions', json={'hotel_id': hotel['id'], 'feature_key': 'sea_view'}).json()
    reply(client, view['id'], 'В номере 502 есть вид на море.')
    parsed = client.post('/api/parse-query', json={'text': QUERY}).json()
    parsed['hard_constraints'].append({'feature_key': 'sea_view', 'operator': '=', 'value': True,
                                       'scope': 'room', 'unit': None})
    assert not client.post('/api/search', json={'parsed': parsed, 'include_simulated': True}).json()['matched']
    reply(client, q['id'], 'В номере 502 есть плотные шторы.')
    matched = client.post('/api/search', json={'parsed': parsed, 'include_simulated': True}).json()['matched']
    assert matched[0]['hotel']['id'] == hotel['id']
    assert matched[0]['recommended_room_id'] == hotel['id'] + ':room:502'


def test_new_feature_conflict_reopens_question_and_is_resolved_by_existing_api(client):
    hotel = client.get('/api/hotels').json()[0]
    q = client.post('/api/hotelier/questions', json={'hotel_id': hotel['id'], 'feature_key': KEY}).json()
    _, first = reply(client, q['id'], POSITIVE)
    reply(client, q['id'], 'В номере 501 нет плотных штор.')
    assert client.get('/api/hotelier/questions', params={'hotel_id': hotel['id'], 'status': 'open'}).json()
    assert not client.post('/api/search', json={'text': QUERY, 'include_simulated': True}).json()['matched']
    conflict = client.get('/api/hotelier/conflicts', params={'hotel_id': hotel['id']}).json()[0]
    resolution = client.post(f'/api/hotelier/conflicts/{conflict["id"]}/resolve', json={
        'selected_observation_id': first['observation_ids'][0], 'reason': 'Проверен ответ о шторах'})
    assert resolution.status_code == 200
    assert resolution.json()['current']['value'] is True
    assert client.post('/api/search', json={'text': QUERY, 'include_simulated': True}).json()['matched']


@pytest.mark.parametrize('phrase', ['неплотные шторы', 'антиблэкаут'])
def test_alias_is_not_matched_inside_a_different_word(client, phrase):
    hotel = client.get('/api/hotels').json()[0]
    q = client.post('/api/hotelier/questions', json={'hotel_id': hotel['id'], 'feature_key': KEY}).json()
    response = client.post(f'/api/hotelier/questions/{q["id"]}/answer',
                           json={'text': f'В номере 501 {phrase}.'})
    assert response.status_code == 200
    extraction = response.json()['extraction']
    assert not extraction['claims'] and extraction['unparsed']


@pytest.mark.parametrize('provider', ['ollama', 'groq'])
def test_guest_model_receives_the_current_registry_and_schema(provider):
    expected = FixtureQueryParser().parse(QUERY)
    text = 'Хочу блэкаут в комнате, чтобы не мешал свет'
    assert FixtureQueryParser().parse(text).unknown_or_ambiguous
    def handler(request):
        payload = json.loads(request.content)
        definitions = json.loads(payload['messages'][0]['content'].split('\nРеестр: ', 1)[1])
        assert definitions[KEY]['scope'] == 'room' and 'плотных штор' in definitions[KEY]['aliases']
        assert definitions[KEY]['description']
        schema = payload['format'] if provider == 'ollama' else payload['response_format']['json_schema']['schema']
        assert KEY in schema['$defs']['HardConstraint']['properties']['feature_key']['enum']
        if provider == 'ollama':
            return httpx.Response(200, json={'message': {'content': expected.model_dump_json()}})
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': expected.model_dump_json()}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        parser = (OllamaQueryParser if provider == 'ollama' else GroqQueryParser)(
            replace(settings, groq_api_key='test-secret'), client=http)
        parsed = parser.parse(text)
        assert parsed.hard_constraints[0].feature_key == KEY and parsed.original_text == text


@pytest.mark.parametrize('provider', ['ollama', 'groq'])
def test_reply_model_receives_the_new_feature_without_special_cases(provider):
    def handler(request):
        payload = json.loads(request.content)
        assert 'плотных штор' in payload['messages'][0]['content']
        schema = payload['format'] if provider == 'ollama' else payload['response_format']['json_schema']['schema']
        assert schema['$defs']['RoomClaim']['properties']['feature_key']['enum'] == [KEY]
        result = json.dumps({'claims': [{'room_number': '501', 'floor': None,
            'feature_key': KEY, 'value': True, 'quote': POSITIVE[:-1]}], 'unparsed': []})
        if provider == 'ollama':
            return httpx.Response(200, json={'done': True, 'done_reason': 'stop', 'message': {'content': result}})
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': result}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        parser = (OllamaReplyParser if provider == 'ollama' else GroqReplyParser)(
            replace(settings, groq_api_key='test-secret'), client=http)
        result = parse_reply(parser, feature_key=KEY, text=POSITIVE)
        assert result.claims[0].feature_key == KEY and not result.unparsed

