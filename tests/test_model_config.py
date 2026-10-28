"""Проверяем контракт общего YAML и передачу параметров обоим провайдерам."""
from dataclasses import replace

import httpx
import json
import pytest
import yaml

from app.core.config import ROOT, settings
from app.core.model_config import load_model_config
from app.ml.query_parser import FixtureQueryParser, OllamaQueryParser, GroqQueryParser


@pytest.mark.parametrize('patch', [
    {'parser_mode': 'typo'}, {'temperature': -1.0}, {'max_output_tokens': 0},
    {'ollama_num_ctx': '8192'}, {'groq_api_key': 'must-not-be-in-shared-config'},
])
def test_invalid_shared_config_fails_early(tmp_path, patch):
    data = yaml.safe_load((ROOT/'config/models.yaml').read_text())
    path = tmp_path/'models.yaml'
    path.write_text(yaml.safe_dump(data | patch))
    with pytest.raises(ValueError, match='ML-конфигурацию'):
        load_model_config(path)


@pytest.mark.parametrize('mode', ['ollama', 'groq'])
def test_shared_yaml_controls_real_provider_payload(tmp_path, mode):
    data = yaml.safe_load((ROOT/'config/models.yaml').read_text())
    path = tmp_path/'models.yaml'
    path.write_text(yaml.safe_dump(data | {
        'parser_mode': mode, 'model_name': 'local-test', 'groq_model': 'cloud-test',
        'temperature': .25, 'max_output_tokens': 512, 'ollama_num_ctx': 4096,
        'parser_timeout_seconds': 17, 'groq_reasoning_effort': 'medium',
    }))
    shared = load_model_config(path)
    config = replace(settings, **shared.model_dump(), groq_api_key='test-only')
    expected = FixtureQueryParser().parse('Нужен номер без вида на море')
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert request.extensions['timeout']['read'] == 17
        if mode == 'ollama':
            assert body['model'] == 'local-test'
            assert body['options'] == {'temperature': .25, 'num_predict': 512, 'num_ctx': 4096}
            return httpx.Response(200, json={'message': {'content': expected.model_dump_json()}})
        assert body['model'] == 'cloud-test'
        assert body['temperature'] == .25 and body['max_completion_tokens'] == 512
        assert body['reasoning_effort'] == 'medium'
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
            'message': {'content': expected.model_dump_json()}}]})

    # Используем настоящий клиент адаптера, подменяя лишь HTTP-транспорт.
    cls = OllamaQueryParser if mode == 'ollama' else GroqQueryParser
    parser = cls(config)
    parser.client.close()
    parser.client = httpx.Client(transport=httpx.MockTransport(handler), timeout=config.parser_timeout_seconds)
    try:
        assert parser.parse(expected.original_text).hard_constraints[0].value is False
        assert len(calls) == 1
    finally:
        parser.client.close()


def test_source_archive_contains_shared_config_but_no_local_env():
    from scripts.package_demo import project_files
    files = project_files()
    assert ROOT/'config/models.yaml' in files
    assert ROOT/'.env' not in files
