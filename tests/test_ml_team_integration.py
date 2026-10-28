"""Регрессии на границах ML → search → кабинет после объединения веток команды."""
import pytest
from app.ml.companions import expand
from app.ml.multicriteria import aggregate
from app.schemas.query import ParsedHotelQuery, SoftPreference


def view_query(value=True):
    return ParsedHotelQuery(soft_preferences=[SoftPreference(
        feature_key='sea_view', scope='room', desired=value, importance=.8, weight_source='explicit')])


def search(client, parsed, weights=None):
    response = client.post('/api/search', json={'parsed': parsed, 'weights': weights or {}})
    assert response.status_code == 200, response.text
    body = response.json()
    # Ответ сервера обязан оставаться допустимым входом для следующего поиска.
    ParsedHotelQuery.model_validate(body['parsed'])
    return body['parsed']


def test_search_weight_roundtrip_and_explicit_companion_override(client):
    parsed = search(client, view_query().model_dump(mode='json'))
    parsed = search(client, parsed, {'sea_view_potential': .3})
    parsed = search(client, parsed, {'sea_view': 0})
    prefs = {p['feature_key']: p for p in parsed['soft_preferences']}
    assert prefs['sea_view_potential']['importance'] == .3
    assert prefs['sea_view_potential']['derived_from'] == 'sea_view'
    assert prefs['sea_view_potential']['weight_source'] == 'explicit'


def test_automatic_companion_follows_parent_weight(client):
    parsed = search(client, view_query().model_dump(mode='json'))
    parsed = search(client, parsed, {'sea_view': 0})
    assert all(p['importance'] == 0 for p in parsed['soft_preferences'])
    parsed = search(client, parsed, {'sea_view': .6})
    companion = next(p for p in parsed['soft_preferences'] if p['feature_key'] == 'sea_view_potential')
    assert companion['importance'] == .6 and companion['weight_source'] == 'companion'


def test_no_view_from_a_room_does_not_mean_no_view_from_whole_building():
    assert [p.feature_key for p in expand(view_query(False)).soft_preferences] == ['sea_view']


def test_small_priority_has_small_penalty_in_balanced_ranking():
    prefs = [SoftPreference(feature_key='quietness_proxy', desired='high', importance=1, weight_source='explicit'),
             SoftPreference(feature_key='sea_view', scope='room', desired=True, importance=.001, weight_source='explicit')]
    result = aggregate(prefs, {'quietness_proxy': 1, 'sea_view': 0})
    assert result['lower'] > .998
    assert result['lower'] == result['upper']
    # При одинаковых весах сохраняем прежнюю интерпретацию баланса.
    prefs[1].importance = 1
    assert aggregate(prefs, {'quietness_proxy': 1, 'sea_view': 0})['lower'] == pytest.approx(.375)


def test_offline_parser_supports_new_team_feature():
    from app.ml.rules_parser import RulesQueryParser
    parsed = RulesQueryParser().parse('Хочу плотные шторы')
    assert any(p.feature_key == 'blackout_curtains' and p.desired is True for p in parsed.soft_preferences)


def test_resolve_route_has_one_handler(client):
    # OpenAPI также проверяется: один контракт используется обоими кабинетами.
    schema = client.get('/openapi.json').json()
    request = schema['components']['schemas']['ResolveConflictRequest']
    assert set(request['required']) == {'selected_observation_id', 'reason'}
