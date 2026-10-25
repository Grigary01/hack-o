"""Streamlit AppTest проходит UI → HTTP-контракт FastAPI без сети и браузера."""
from streamlit.testing.v1 import AppTest
from frontend.api_client import APIClient
from app.core.config import ROOT


def test_search_and_hotelier_screen(client,monkeypatch):
    def request(self,method,path,payload=None):
        response=client.request(method,path,json=payload)
        if response.is_error:
            raise RuntimeError(str(response.json()))
        return response.json()
    monkeypatch.setattr(APIClient,'request',request)
    ui=AppTest.from_file(ROOT/'frontend/app.py',default_timeout=20).run()
    assert not ui.exception
    next(b for b in ui.button if b.label=='Найти отели').click().run()
    assert not ui.exception
    assert any('Соответствуют по имеющимся данным · 12' in h.value for h in ui.subheader)
    assert len(ui.slider)==2
    ui.slider[0].set_value(.2).run()
    assert not ui.exception
    next(b for b in ui.button if b.label=='Сформировать вопрос').click().run()
    next(a for a in ui.text_area if a.label=='Ответ своими словами').set_value('В номерах 301–305 вид на море, все на 3-м этаже.')
    next(b for b in ui.button if b.label=='Разобрать ответ').click().run()
    assert not ui.exception
    next(b for b in ui.button if b.label=='Подтвердить разбор').click().run()
    assert not ui.exception
    assert any('Решение сохранено' in s.value for s in ui.success)
