import pytest
from streamlit.testing.v1 import AppTest
from app.core.config import ROOT
from frontend.api_client import APIClient, APIError
from frontend import hotelier_view
from app.ml.query_parser import FixtureQueryParser


def setup_conflict(client):
    hotel = client.get('/api/hotels').json()[0]
    q = client.post('/api/hotelier/questions', json={'hotel_id': hotel['id'], 'feature_key': 'sea_view'}).json()
    ids = []
    for text in ('В номере 301 есть вид на море.', 'В номере 301 нет вида на море.'):
        a = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json={'text': text}).json()
        result = client.post(f'/api/hotelier/answers/{a["id"]}/confirm', json={'accept': True}).json()
        ids += result['observation_ids']
    return hotel, q, ids


def ui_for(client, monkeypatch, error=None):
    state = {'resolved': False, 'searches': []}
    def request(self, method, path, payload=None):
        if path == '/api/search':
            state['searches'].append(payload)
            if error == 'refresh' and state['resolved']:
                raise APIError(503, 'Учебный отказ поиска', 'service_unavailable')
        if path.endswith('/resolve') and method == 'POST' and error == 'conflict':
            raise APIError(409, 'Решение уже изменено другим оператором', 'state_conflict')
        response = client.request(method, path, json=payload)
        if response.is_error:
            raise APIError(response.status_code, response.json()['detail'], response.json().get('code'))
        if path.endswith('/resolve') and method == 'POST':
            state['resolved'] = True
        return response.json()
    monkeypatch.setattr(APIClient, 'request', request)
    return AppTest.from_file(ROOT / 'frontend/app.py', default_timeout=20).run(), state


def select_and_search(ui, qid, simulated):
    next(s for s in ui.selectbox if s.label == 'Вопросы агента').set_value(qid).run()
    next(a for a in ui.text_area if a.label == 'Что важно в поездке?').set_value('Нужен номер обязательно с видом на море')
    next(c for c in ui.checkbox if c.label == 'Учитывать симулированные ответы отельера').set_value(simulated)
    next(b for b in ui.button if b.label == 'Найти отели').click().run()
    assert not ui.exception


@pytest.mark.parametrize(('positive', 'simulated'), [(True, True), (False, True), (True, False)])
def test_conflict_resolved_in_ui_refreshes_question_evidence_and_search(client, monkeypatch, positive, simulated):
    hotel, q, ids = setup_conflict(client)
    ui, state = ui_for(client, monkeypatch)
    select_and_search(ui, q['id'], simulated)
    button = next(b for b in ui.button if b.label == 'Сохранить решение')
    assert button.disabled
    assert any('Вопрос снова требует' in x.value for x in ui.warning)
    assert any('Версия 1:' in m.value for m in ui.markdown)
    next(r for r in ui.radio if r.label == 'Какую версию сохранить?').set_value(ids[0] if positive else ids[1]).run()
    assert next(b for b in ui.button if b.label == 'Сохранить решение').disabled
    next(a for a in ui.text_area if a.label == 'Почему выбрана эта версия?').set_value('Проверено по исходному ответу').run()
    next(b for b in ui.button if b.label == 'Сохранить решение').click().run()
    assert not ui.exception
    assert any('Решение сохранено' in s.value for s in ui.success)
    assert any('Уточнение закрыто' in s.value for s in ui.success)
    expected = 1 if positive and simulated else 0
    assert any(f'Соответствуют по имеющимся данным · {expected}' in s.value for s in ui.subheader)
    assert not any(b.label == 'Сохранить решение' for b in ui.button)
    assert state['searches'][-1]['include_simulated'] is simulated
    assert state['searches'][-1]['ranking_method'] == 'balanced_v2'
    assert state['searches'][-1]['balance'] == .25
    assert state['searches'][-1].get('parsed')
    evidence = client.get(f'/api/hotels/{hotel["id"]}/evidence').json()
    assert len([o for o in evidence['observations'] if o['feature_key'] == 'sea_view']) == 2


@pytest.mark.parametrize('error', ['conflict', 'refresh'])
def test_resolve_errors_do_not_show_false_success_or_stale_results(client, monkeypatch, error):
    hotel, q, ids = setup_conflict(client)
    ui, state = ui_for(client, monkeypatch, error=error)
    select_and_search(ui, q['id'], True)
    next(r for r in ui.radio if r.label == 'Какую версию сохранить?').set_value(ids[0]).run()
    next(a for a in ui.text_area if a.label == 'Почему выбрана эта версия?').set_value('Причина решения').run()
    next(b for b in ui.button if b.label == 'Сохранить решение').click().run()
    assert not ui.exception
    if error == 'conflict':
        assert any('409' in e.value for e in ui.error)
        assert not any('Решение сохранено' in s.value for s in ui.success)
        assert client.get('/api/hotelier/conflicts', params={'status': 'open', 'hotel_id': hotel['id']}).json()
    else:
        assert any('Решение сохранено' in s.value for s in ui.success)
        assert any('Не удалось обновить подбор' in w.value for w in ui.warning)
        assert not any('Соответствуют по имеющимся данным' in s.value for s in ui.subheader)
        assert not client.get('/api/hotelier/conflicts', params={'status': 'open', 'hotel_id': hotel['id']}).json()


def test_owner_refresh_keeps_custom_weights_balance_and_method_without_reparsing_text(client, monkeypatch):
    hotel = client.get('/api/hotels').json()[0]
    previous = client.post('/api/search', json={
        'text': FixtureQueryParser().examples[0]['text'], 'weights': {'quietness_proxy': .2},
        'balance': .65, 'ranking_method': 'weighted_v1', 'include_simulated': True}).json()
    session = {'response': previous}
    calls = []
    class Transport:
        def post(self, path, payload):
            calls.append(payload)
            response = client.post(path, json=payload)
            response.raise_for_status()
            return response.json()
        def get(self, path):
            return client.get(path).json()
    class Rerun(Exception):
        pass
    def rerun():
        raise Rerun()
    monkeypatch.setattr(hotelier_view.st, 'session_state', session)
    monkeypatch.setattr(hotelier_view.st, 'rerun', rerun)
    with pytest.raises(Rerun):
        hotelier_view.finish_owner_action(Transport(), hotel['id'], {'status': 'resolved', 'current': {'value': True}})
    assert calls[0]['weights']['quietness_proxy'] == .2
    assert calls[0]['balance'] == .65 and calls[0]['ranking_method'] == 'weighted_v1'
    assert calls[0]['include_simulated'] is True and 'text' not in calls[0]
    assert session['response']['balance'] == .65
