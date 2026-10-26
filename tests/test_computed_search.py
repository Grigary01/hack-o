"""Сквозной поиск по расчётным характеристикам и сверка ответа отельера с расчётом."""
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from app.features.registry import get_registry
from app.ml.companions import expand
from app.ml.query_parser import FixtureQueryParser, llm_schema
from app.ml.ranking import soft_match

# Расчёт вида датирован состоянием OSM на 25.10.2026; общий TEST_NOW (23.10) раньше.
LATER = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
OFELIA = 'osm:node:11843553838'      # море с 3-го этажа, под глиссадой ВПП 06
CHERNOMOR = 'osm:node:11138786325'   # моря не видно ни с одного этажа


@pytest.fixture(autouse=True)
def after_viewshed_snapshot(monkeypatch):
    for module in ('app.storage.repository', 'app.features.service', 'app.hotelier.dialogue', 'app.agent.feature_agent'):
        monkeypatch.setattr(module + '.now_utc', lambda: LATER)


def test_ordinal_categories_give_partial_credit():
    pref = SimpleNamespace(utility=None, feature_key='sea_view_potential', desired='wide')
    assert [soft_match(v, pref) for v in ('none', 'partial', 'wide')] == [0., .5, 1.]
    quiet = SimpleNamespace(utility=None, feature_key='quietness_proxy', desired='high')
    assert soft_match('medium', quiet) == .5


def test_companions_follow_registry_and_respect_negation():
    parser = FixtureQueryParser()
    expanded = expand(parser.parse('Нужен номер обязательно с видом на море'))
    companion = next(p for p in expanded.soft_preferences if p.feature_key == 'sea_view_potential')
    assert companion.desired == 'wide' and companion.derived_from == 'sea_view'
    assert not expanded.hard_constraints[0].feature_key.endswith('potential')  # hard не ужесточается
    negative = expand(parser.parse('Нужен номер без вида на море'))
    assert negative.soft_preferences[0].desired == 'none'
    assert expand(expanded).soft_preferences == expanded.soft_preferences  # идемпотентно
    # LLM не видит полей, которые заполняет только backend.
    soft = llm_schema()['$defs']['SoftPreference']['properties']
    assert 'derived_from' not in soft and 'companion' not in soft['weight_source']['enum']


def test_search_explains_floor_side_and_aircraft(client):
    text = FixtureQueryParser().examples[0]['text']
    body = client.post('/api/search', json={'text': text}).json()
    keys = [p['feature_key'] for p in body['parsed']['soft_preferences']]
    assert keys[-2:] == ['aircraft_path_distance_m', 'sea_view_potential']
    rows = body['matched'] + body['needs_verification'] + body['excluded']  # Офелия дальше 500 м от пляжа
    ofelia = next(r for r in rows if r['hotel']['id'] == OFELIA)
    by_key = {c['feature_key']: c for c in ofelia['criteria']}
    assert by_key['sea_view_potential']['actual'] == 'wide'
    assert 'с 3-го этажа' in by_key['sea_view_potential']['explanation']
    assert 'стороны ЮЗ' in by_key['sea_view_potential']['explanation']
    assert 'от окна 3-го этажа' in by_key['aircraft_path_distance_m']['explanation']
    assert by_key['aircraft_path_distance_m']['match'] < .1  # 78 м до траектории — почти ноль
    # Вес спутника настраивается, повторный поиск по parsed не дублирует его.
    again = client.post('/api/search', json={'parsed': body['parsed'],
                                             'weights': {'aircraft_path_distance_m': 1.0}}).json()
    assert [p['feature_key'] for p in again['parsed']['soft_preferences']] == keys


def answer(client, hotel_id, text):
    q = client.post('/api/hotelier/questions', json={'hotel_id': hotel_id, 'feature_key': 'sea_view'}).json()
    a = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': text}).json()
    return q, client.post(f'/api/hotelier/answers/{a["id"]}/confirm', json={'accept': True}).json()


def test_hotelier_floor_below_model_is_flagged_not_hidden(client):
    question, confirmed = answer(client, OFELIA, 'В номере 201 вид на море, это 2-й этаж.')
    assert 'с 3-го этажа' in question['text']  # агент спрашивает с подсказкой из расчёта
    assert [r['reason'] for r in confirmed['model_review']] == ['below_model_min_floor']
    assert any(c['policy'] == 'review:below_model_min_floor' for c in confirmed['conflicts'])
    body = client.post('/api/search', json={'text': 'Нужен номер обязательно с видом на море',
                                            'include_simulated': True}).json()
    ofelia = next(r for r in body['matched'] if r['hotel']['id'] == OFELIA)
    room = next(c for c in ofelia['criteria'] if c['feature_key'] == 'sea_view')
    # Значение отельера остаётся (номер подходит), но расхождение видно гостю.
    assert room['actual'] is True and room['model_conflicts'][0]['reason'] == 'below_model_min_floor'
    assert '⚠' in room['explanation'] and any('расходится с расчётом' in w for w in ofelia['warnings'])


def test_hotelier_claim_where_model_sees_no_sea(client):
    _, confirmed = answer(client, CHERNOMOR, 'В номере 305 вид на море.')
    assert [r['reason'] for r in confirmed['model_review']] == ['model_sees_none']
    _, negative = answer(client, CHERNOMOR, 'В номере 306 нет вида на море.')
    assert negative['model_review'] == []  # «нет вида» расчёту не противоречит


def test_registry_rejects_bad_companion(tmp_path):
    from app.features.registry import FeatureRegistry
    bad = tmp_path / 'registry.yaml'
    bad.write_text(get_registry_text().replace('desired_if_true: wide', 'desired_if_true: huge'))
    with pytest.raises(ValueError):
        FeatureRegistry(bad)


def get_registry_text():
    from app.core.config import settings
    return settings.registry_path.read_text()
