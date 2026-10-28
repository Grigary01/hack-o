"""Снимки состояний для разработки экрана. Не имитирует parser/подтверждение."""
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


class StubQuestionAPI:
    def __init__(self, scenario='open', fixture_path=None):
        path = fixture_path if fixture_path is not None else (
            Path(__file__).resolve().parents[1] / 'docs/examples/question_integration_fixture.json')
        self.fixture = json.loads(Path(path).read_text())
        self.show(scenario)

    def show(self, scenario):
        if scenario not in self.fixture['question_states']:
            raise ValueError('Неизвестный сценарий заглушки')
        self.scenario = scenario

    def get(self, path):
        url = urlsplit(path)
        if url.path != '/api/hotelier/questions':
            raise RuntimeError('Заглушка поддерживает только очередь вопросов')
        question = self.fixture['question_states'][self.scenario]
        filters = parse_qs(url.query)
        if any(question[key] != values[0] for key, values in filters.items() if key in ('hotel_id', 'status')):
            return []
        return [deepcopy(question)]

    def post(self, path, payload):
        if path == '/api/hotelier/questions' and payload == self.fixture['question_request']:
            return deepcopy(self.fixture['question_states'][self.scenario])
        raise RuntimeError('Отправку и подтверждение ответа проверяйте с backend; для экрана выберите stub.show(...)')
