"""Streamlit AppTest: отельер исправляет расчёт, оператор разрешает конфликт."""
from datetime import datetime, timezone
from streamlit.testing.v1 import AppTest
from frontend.api_client import APIClient
from app.core.config import ROOT

LATER = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)


def test_correct_fact_then_resolve_conflict(client, monkeypatch):
    for module in ('app.storage.repository', 'app.features.service', 'app.hotelier.dialogue',
                   'app.agent.feature_agent', 'app.hotelier.review'):
        monkeypatch.setattr(module + '.now_utc', lambda: LATER)

    def request(self, method, path, payload=None):
        response = client.request(method, path, json=payload)
        if response.is_error:
            raise RuntimeError(str(response.json()))
        return response.json()
    monkeypatch.setattr(APIClient, 'request', request)
    ui = AppTest.from_file(ROOT / 'frontend/app.py', default_timeout=30).run()
    assert not ui.exception
    ui.radio(key='verdict_sea_view_potential').set_value('Исправить')
    ui.selectbox(key='value_sea_view_potential').set_value('море в просвете')
    ui.button(key='submit_sea_view_potential').click().run()
    assert not ui.exception
    assert any('Конфликты источников · открыто 1' in h.value for h in ui.subheader)
    choose = next(r for r in ui.radio if r.label == 'Какая версия верна')
    choose.set_value(next(o for o in choose.options if 'Отельер' in o))
    next(t for t in ui.text_input if t.label == 'Причина решения').input('Деревья перед окнами')
    next(b for b in ui.button if b.label == 'Разрешить конфликт').click().run()
    assert not ui.exception
    assert any('Конфликты источников · открыто 0' in h.value for h in ui.subheader)
    assert any('Деревья перед окнами' in s.value for s in ui.success)
