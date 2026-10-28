import pytest
from streamlit.testing.v1 import AppTest
from app.core.config import ROOT
from app.core.errors import ReplyParserUnavailable
from frontend.api_client import APIClient


@pytest.mark.parametrize('change', ['parse_failure', 'edited_text', 'question_change'])
def test_stale_preview_cannot_be_confirmed_after_input_or_parser_changes(client, monkeypatch, change):
    def request(self, method, path, payload=None):
        response = client.request(method, path, json=payload)
        if response.is_error:
            raise RuntimeError(response.json()['detail'])
        return response.json()
    monkeypatch.setattr(APIClient, 'request', request)
    hotels = client.get('/api/hotels').json()
    for hotel in hotels[:2]:
        client.post('/api/hotelier/questions', json={'hotel_id': hotel['id'], 'feature_key': 'sea_view'})
    ui = AppTest.from_file(ROOT / 'frontend/app.py', default_timeout=20).run()
    next(a for a in ui.text_area if a.label == 'Ответ своими словами').set_value('В номере 301 есть вид на море.')
    next(b for b in ui.button if b.label == 'Разобрать ответ').click().run()
    assert not ui.exception
    assert any(b.label == 'Подтвердить разбор' for b in ui.button)
    if change == 'parse_failure':
        class Unavailable:
            mode = 'stub_unavailable'
            def parse(self, *, feature_key, text):
                raise ReplyParserUnavailable('Учебный отказ модели')
        client.app.state.reply_parser = Unavailable()
        next(b for b in ui.button if b.label == 'Разобрать ответ').click().run()
        assert any('Учебный отказ' in e.value for e in ui.error)
    elif change == 'edited_text':
        next(a for a in ui.text_area if a.label == 'Ответ своими словами').set_value('В номере 302 нет вида на море.')
        ui.run()
    else:
        selector = next(s for s in ui.selectbox if s.label == 'Вопросы агента')
        other = next(q['id'] for q in client.get('/api/hotelier/questions').json() if q['id'] != selector.value)
        selector.set_value(other).run()
    assert not ui.exception
    assert not any(b.label == 'Подтвердить разбор' for b in ui.button)
