"""Явная заглушка для frontend без backend/LLM. Поддерживает один пример контракта.

Это не альтернативный resolver. Значения и выбранный ответ взяты из JSON,
выгруженного настоящим API; для других случаев нужен backend.
"""
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


class StubConflictAPI:
    def __init__(self, fixture_path=None):
        path = fixture_path if fixture_path is not None else (
            Path(__file__).resolve().parents[1] / 'docs/examples/conflict_integration_fixture.json')
        self.fixture = json.loads(Path(path).read_text())
        self.resolved = False

    def get(self, path):
        url = urlsplit(path)
        if url.path != '/api/hotelier/conflicts':
            raise RuntimeError('Заглушка поддерживает только список конфликтов')
        row = self.fixture['resolved_conflict' if self.resolved else 'open_conflict']
        filters = parse_qs(url.query)
        if any(row[key] != values[0] for key, values in filters.items() if key in ('hotel_id', 'status')):
            return []
        return [deepcopy(row)]

    def post(self, path, payload):
        expected_path = f'/api/hotelier/conflicts/{self.fixture["open_conflict"]["id"]}/resolve'
        if path != expected_path or payload != self.fixture['resolution_request']:
            raise RuntimeError('Для заглушки используйте resolution_request из conflict_integration_fixture.json')
        result = deepcopy(self.fixture['resolution_response'])
        result['idempotent'] = self.resolved
        self.resolved = True
        return result
