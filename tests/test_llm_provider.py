"""Переключатель модели LLM_PROVIDER и подстраховка облачного режима."""
import json
import os
import subprocess
import sys

import pytest

from app.core.config import ROOT
from app.ml.query_parser import CloudWithRulesFallback, QueryParserUnavailable, ParserError


def config_with(**env):
    """Конфигурация читается при импорте — проверяем в отдельном процессе с нужным окружением."""
    # Пустые значения явно: python-dotenv не перезаписывает заданные переменные локальным .env.
    keys = ('LLM_PROVIDER', 'PARSER_MODE', 'HYBRID_LLM', 'LLM_API_KEY', 'GROQ_API_KEY',
            'LOCAL_LLM_MODEL', 'CLOUD_LLM_BASE_URL', 'CLOUD_LLM_MODEL')
    clean = {**os.environ, **{k: '' for k in keys}}
    code = ('import json; from app.core.config import settings as s; from app.main import describe_llm;'
            'print(json.dumps({"mode": s.parser_mode, "hybrid": s.hybrid_llm, "model": s.model_name,'
            '"key": bool(s.groq_api_key), "fallback": s.cloud_rules_fallback, "llm": describe_llm(s)}))')
    out = subprocess.run([sys.executable, '-c', code], env={**clean, **env, 'PYTHONPATH': str(ROOT)},
                         cwd=ROOT, capture_output=True, text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_provider_presets():
    cloud = config_with(LLM_PROVIDER='cloud', LLM_API_KEY='k', CLOUD_LLM_MODEL='claude-opus-5')
    assert (cloud['mode'], cloud['key'], cloud['fallback']) == ('groq', True, True)
    assert cloud['llm'].startswith('облако: claude-opus-5') and 'правила' in cloud['llm']
    local = config_with(LLM_PROVIDER='local')
    assert (local['mode'], local['hybrid'], local['model']) == ('hybrid', 'ollama', 'gemma3:12b')
    assert config_with(LLM_PROVIDER='off')['mode'] == 'offline'
    # Явный PARSER_MODE сильнее переключателя, и тогда ошибка модели не скрывается.
    explicit = config_with(LLM_PROVIDER='cloud', PARSER_MODE='groq')
    assert (explicit['mode'], explicit['fallback']) == ('groq', False)
    # Прежнее имя ключа работает.
    assert config_with(LLM_PROVIDER='cloud', GROQ_API_KEY='old')['key'] is True


def test_unknown_provider_is_rejected():
    env = {**os.environ, 'LLM_PROVIDER': 'gpt', 'PARSER_MODE': '', 'PYTHONPATH': str(ROOT)}
    result = subprocess.run([sys.executable, '-c', 'import app.core.config'], env=env, cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode != 0 and 'LLM_PROVIDER' in result.stderr


class BrokenCloud:
    client = None

    def __init__(self, exc):
        self.exc = exc

    def parse(self, text):
        raise self.exc


@pytest.mark.parametrize('exc', [QueryParserUnavailable('HTTP 429'), ParserError('невалидный ответ')])
def test_cloud_failure_falls_back_to_rules_and_says_so(exc):
    parser = CloudWithRulesFallback(BrokenCloud(exc))
    parsed = parser.parse('Тихий отель у моря')
    assert parser.current_mode() == 'rules_fallback'
    assert {p.feature_key for p in parsed.soft_preferences} >= {'quietness_proxy'}


def test_working_cloud_is_used_as_is():
    class Cloud:
        client = None

        def parse(self, text):
            from app.schemas.query import ParsedHotelQuery
            return ParsedHotelQuery(original_text=text)
    parser = CloudWithRulesFallback(Cloud())
    assert parser.parse('что угодно').original_text == 'что угодно'
    assert parser.current_mode() == 'groq'


def test_search_reports_rules_fallback(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.storage.db import create_db
    from scripts.seed_demo import seed
    engine = create_db(f'sqlite:///{tmp_path / "t.db"}')
    seed(engine)
    client = TestClient(create_app(engine=engine, parser=CloudWithRulesFallback(BrokenCloud(QueryParserUnavailable('нет сети')))))
    body = client.post('/api/search', json={'text': 'Тихий отель у моря'}).json()
    assert body['status'] == 'ok' and body['parser_mode'] == 'rules_fallback'
