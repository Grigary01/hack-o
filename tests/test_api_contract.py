from dataclasses import replace
import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from app.ml.query_parser import FixtureQueryParser, OllamaQueryParser, GroqQueryParser, ParserError
from app.schemas.errors import APIError
from app.schemas.hotel_views import HotelDetail, HotelEvidence, HealthResponse
from app.schemas.hotelier import HotelierAnswer, AnswerConfirmation


def pending(client):
    hotel = client.get('/api/hotels').json()[0]
    q = client.post('/api/hotelier/questions', json={'hotel_id': hotel['id'], 'feature_key': 'sea_view'}).json()
    answer = client.post(f'/api/hotelier/questions/{q["id"]}/answer',
                         json={'text': 'В номерах 301–302 есть вид на море.'}).json()
    return hotel, q, answer


def test_typed_responses_and_repeat_confirmation_preserve_saved_information(client):
    HealthResponse.model_validate(client.get('/api/health').json())
    hotel, q, raw = pending(client)
    answer = HotelierAnswer.model_validate(raw)
    assert answer.status == 'pending'
    loaded = client.get(f'/api/hotelier/answers/{answer.id}')
    assert loaded.status_code == 200 and loaded.json() == raw
    path = f'/api/hotelier/answers/{answer.id}/confirm'
    first = AnswerConfirmation.model_validate(client.post(path, json={'accept': True}).json())
    repeated = AnswerConfirmation.model_validate(client.post(path, json={'accept': True}).json())
    assert first.status == repeated.status == 'confirmed'
    assert repeated.idempotent and not first.idempotent
    assert first.observation_ids == repeated.observation_ids and len(first.observation_ids) == 2
    assert first.question.id == q['id'] and first.question.status == 'answered'
    assert HotelierAnswer.model_validate(client.get(f'/api/hotelier/answers/{answer.id}').json()).status == 'confirmed'
    detail = HotelDetail.model_validate(client.get(f'/api/hotels/{hotel["id"]}').json())
    evidence = HotelEvidence.model_validate(client.get(f'/api/hotels/{hotel["id"]}/evidence').json())
    assert {o.id for o in detail.observations} == {o.id for o in evidence.observations}
    assert all(s.value is None for s in evidence.current_real if s.feature_key == 'sea_view')


def test_incompatible_confirmation_is_409_and_bad_boolean_is_422(client):
    _, _, answer = pending(client)
    path = f'/api/hotelier/answers/{answer["id"]}/confirm'
    bad = client.post(path, json={'accept': 'yes'})
    assert bad.status_code == 422 and APIError.model_validate(bad.json()).code == 'invalid_request'
    rejected = AnswerConfirmation.model_validate(client.post(path, json={'accept': False}).json())
    assert rejected.status == 'rejected' and rejected.observation_ids == [] and rejected.source_type is None
    conflict = client.post(path, json={'accept': True})
    assert conflict.status_code == 409 and APIError.model_validate(conflict.json()).code == 'state_conflict'


@pytest.mark.parametrize('path', ['/api/hotels/missing', '/api/hotels/missing/evidence',
                                 '/api/hotelier/answers/missing', '/missing-route'])
def test_not_found_errors_have_stable_code_and_legacy_detail(client, path):
    response = client.get(path)
    assert response.status_code == 404
    body = APIError.model_validate(response.json())
    assert body.code == 'not_found' and isinstance(body.detail, str)


def test_validation_details_remain_structured_and_balance_is_reported(client):
    bad = client.post('/api/search', json={})
    error = APIError.model_validate(bad.json())
    assert bad.status_code == 422 and isinstance(error.detail, list)
    assert error.detail[0]['loc'] == ['body']
    query = FixtureQueryParser().examples[0]['text']
    for method in ('balanced_v2', 'weighted_v1'):
        response = client.post('/api/search', json={'text': query, 'balance': .65, 'ranking_method': method})
        assert response.status_code == 200
        result = response.json()
        assert result['balance'] == .65 and result['ranking_method'] == method
        assert {'matched', 'needs_verification', 'excluded', 'include_simulated'} <= result.keys()


def test_openapi_declares_success_and_error_models_for_integration(client):
    paths = client.get('/openapi.json').json()['paths']
    required = [('/api/health', 'get'), ('/api/hotels', 'get'), ('/api/hotels/{hotel_id}', 'get'),
                ('/api/hotels/{hotel_id}/evidence', 'get'), ('/api/hotelier/questions', 'get'),
                ('/api/hotelier/questions/{qid}/answer', 'post'), ('/api/hotelier/answers/{aid}', 'get'),
                ('/api/hotelier/answers/{aid}/confirm', 'post'), ('/api/hotelier/conflicts', 'get'),
                ('/api/hotelier/conflicts/{conflict_id}/resolve', 'post')]
    for path, method in required:
        responses = paths[path][method]['responses']
        assert responses['200']['content']['application/json']['schema']
        assert responses['422']['content']['application/json']['schema']['$ref'].endswith('/APIError')


@pytest.mark.parametrize('provider', ['ollama', 'groq'])
def test_unavailable_query_provider_is_503_and_keeps_parser_error_compatibility(engine, provider):
    def handler(request):
        raise httpx.ConnectError('private upstream detail', request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        parser = (OllamaQueryParser if provider == 'ollama' else GroqQueryParser)(
            replace(settings, groq_api_key='test-secret'), client=http)
        with TestClient(create_app(engine=engine, parser=parser)) as client:
            response = client.post('/api/parse-query', json={'text': 'Новый свободный запрос'})
            assert response.status_code == 503
            assert APIError.model_validate(response.json()).code == 'service_unavailable'
            assert 'private upstream detail' not in response.text and 'test-secret' not in response.text


def test_invalid_model_output_is_502_and_demo_guard_is_403(engine):
    class Broken:
        mode = 'stub'
        def parse(self, text):
            raise ParserError('Невалидный контракт модели')
    with TestClient(create_app(engine=engine, parser=Broken())) as client:
        response = client.post('/api/parse-query', json={'text': 'Запрос'})
        assert response.status_code == 502 and response.json()['code'] == 'invalid_model_output'
    with TestClient(create_app(engine=engine, parser=FixtureQueryParser(), config=replace(settings, demo_mode=False))) as client:
        response = client.get('/api/hotelier/questions')
        assert response.status_code == 403 and response.json()['code'] == 'forbidden'
