"""Кабинет: проверка расчётных фактов отельером и разрешение конфликтов оператором."""
from datetime import datetime, timezone
import pytest

LATER = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)  # после снимка зданий 25.10
OFELIA = 'osm:node:11843553838'


@pytest.fixture(autouse=True)
def after_viewshed_snapshot(monkeypatch):
    clock = {'now': LATER}
    for module in ('app.storage.repository', 'app.features.service', 'app.hotelier.dialogue',
                   'app.agent.feature_agent', 'app.hotelier.review'):
        monkeypatch.setattr(module + '.now_utc', lambda: clock['now'])
    return clock


def tick(clock, minutes=1):
    from datetime import timedelta
    clock['now'] = clock['now'] + timedelta(minutes=minutes)


def facts(client, hotel_id=OFELIA):
    return {f['feature_key']: f for f in client.get(f'/api/hotelier/hotels/{hotel_id}/facts').json()['facts']}


def test_hotelier_sees_computed_facts_with_explanations(client):
    current = facts(client)
    assert current['sea_view_potential']['display'] == 'широкий вид'
    assert 'с 3-го этажа' in current['sea_view_potential']['explanation']
    assert 'от окна' in current['aircraft_path_distance_m']['explanation']


def test_confirm_keeps_value_correct_creates_conflict_and_operator_resolves(client, after_viewshed_snapshot):
    clock = after_viewshed_snapshot
    confirmed = client.post('/api/hotelier/facts/review', json={'hotel_id': OFELIA, 'feature_key': 'sunset_view_potential',
                                                                'verdict': 'confirm'}).json()
    assert confirmed['value'] == 'year_round' and not confirmed['conflicts']
    tick(clock)
    corrected = client.post('/api/hotelier/facts/review', json={
        'hotel_id': OFELIA, 'feature_key': 'sea_view_potential', 'verdict': 'correct', 'value': 'partial',
        'comment': 'Перед отелем растут высокие кипарисы'}).json()
    assert len(corrected['conflicts']) == 1
    after = facts(client)['sea_view_potential']
    assert after['status'] == 'conflicted' and after['value'] is None  # поиск не берёт ни одну версию
    conflict = corrected['conflicts'][0]
    tick(clock)
    decision = client.post(f'/api/hotelier/conflicts/{conflict["id"]}/resolve', json={
        'chosen_observation_id': corrected['observation_id'], 'reason': 'Деревья модель не учитывает'}).json()
    assert decision['value'] == 'partial'
    resolved = facts(client)['sea_view_potential']
    assert resolved['value'] == 'partial' and resolved['status'] != 'conflicted'
    listed = client.get(f'/api/hotelier/hotels/{OFELIA}/facts').json()['conflicts']
    assert next(c for c in listed if c['id'] == conflict['id'])['resolution']['reason'] == 'Деревья модель не учитывает'
    # Решение по демо-ответу в реальный поиск не попадает: там остаётся расчёт.
    text = 'Ищу тихий отель в Адлере, не дальше 500 метров пешком от пляжа, хотелось бы вид на море'
    real = client.post('/api/search', json={'text': text}).json()
    ofelia = next(r for g in ('matched', 'needs_verification', 'excluded') for r in real[g] if r['hotel']['id'] == OFELIA)
    assert next(c for c in ofelia['criteria'] if c['feature_key'] == 'sea_view_potential')['actual'] == 'wide'


def test_resolution_validates_choice_and_correction_needs_value(client):
    bad = client.post('/api/hotelier/facts/review', json={'hotel_id': OFELIA, 'feature_key': 'sea_view_potential',
                                                          'verdict': 'correct'})
    assert bad.status_code == 422
    wrong = client.post('/api/hotelier/facts/review', json={'hotel_id': OFELIA, 'feature_key': 'sea_view_potential',
                                                            'verdict': 'correct', 'value': 'huge'})
    assert wrong.status_code == 422
    corrected = client.post('/api/hotelier/facts/review', json={
        'hotel_id': OFELIA, 'feature_key': 'sea_view_potential', 'verdict': 'correct', 'value': 'none'}).json()
    conflict = corrected['conflicts'][0]
    other = client.post(f'/api/hotelier/conflicts/{conflict["id"]}/resolve',
                        json={'chosen_observation_id': 'not-in-conflict', 'reason': 'ошибка'})
    assert other.status_code == 422


def test_operator_can_side_with_model_on_room_claim(client, after_viewshed_snapshot):
    clock = after_viewshed_snapshot
    q = client.post('/api/hotelier/questions', json={'hotel_id': OFELIA, 'feature_key': 'sea_view'}).json()
    a = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': 'В номере 201 вид на море, это 2-й этаж.'}).json()
    confirmed = client.post(f'/api/hotelier/answers/{a["id"]}/confirm', json={'accept': True}).json()
    review = next(c for c in confirmed['conflicts'] if c['policy'].startswith('review:'))
    model_id = next(i for i in (review['left_id'], review['right_id']) if not i.startswith(a['id']))
    tick(clock)
    decision = client.post(f'/api/hotelier/conflicts/{review["id"]}/resolve',
                           json={'chosen_observation_id': model_id, 'reason': 'Со 2-го этажа море закрывает дом'}).json()
    assert decision['value'] is False
    body = client.post('/api/search', json={'text': 'Нужен номер обязательно с видом на море', 'include_simulated': True}).json()
    assert OFELIA not in [r['hotel']['id'] for r in body['matched']]
