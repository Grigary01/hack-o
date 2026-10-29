"""Одни примеры проверяют контракт API, frontend-заглушки и чистого ML-вызова."""
from datetime import timedelta
import json

from app.core.config import ROOT
from app.ml.ranking import rank_hotels
from app.schemas.conflicts import ConflictDetail, ResolveConflictRequest, ResolveConflictResponse
from app.schemas.hotel import Hotel
from app.schemas.query import ParsedHotelQuery
from frontend.conflict_client import ConflictClient
from frontend.conflict_stub import StubConflictAPI


def test_frontend_stub_uses_the_real_api_contract_and_can_be_swapped():
    stub = StubConflictAPI()
    client = ConflictClient(api=stub)
    conflict = ConflictDetail.model_validate(client.list_conflicts(status='open')[0])
    request = ResolveConflictRequest.model_validate(stub.fixture['resolution_request'])
    body = client.resolve_conflict(conflict.id, request.selected_observation_id, request.reason)
    response = ResolveConflictResponse.model_validate(body)
    assert response.current.value is True and not response.idempotent
    assert not client.list_conflicts(status='open')
    resolved = ConflictDetail.model_validate(client.list_conflicts(status='resolved')[0])
    assert resolved.resolution == response.resolution
    assert client.resolve_conflict(conflict.id, request.selected_observation_id, request.reason)['idempotent']
    assert not client.list_conflicts(hotel_id='another-hotel')
    body['current']['value'] = False
    assert client.resolve_conflict(conflict.id, request.selected_observation_id, request.reason)['current']['value'] is True


def test_ml_consumes_contract_without_http_database_or_model(monkeypatch):
    fixture = json.loads((ROOT / 'docs/examples/conflict_integration_fixture.json').read_text())
    hotel = Hotel.model_validate(fixture['hotel'])
    query = ParsedHotelQuery.model_validate(fixture['parsed_query'])
    opened = ConflictDetail.model_validate(fixture['open_conflict'])
    resolved = ConflictDetail.model_validate(fixture['resolved_conflict'])
    facts = [opened.left_observation, opened.right_observation]
    monkeypatch.setattr('app.features.service.now_utc', lambda: resolved.resolution.resolved_at + timedelta(seconds=1))
    assert not rank_hotels(query, [(hotel, facts)], True, conflicts=[opened])['matched']
    assert rank_hotels(query, [(hotel, facts)], True, conflicts=[resolved])['matched']
    assert not rank_hotels(query, [(hotel, facts)], False, conflicts=[resolved])['matched']
