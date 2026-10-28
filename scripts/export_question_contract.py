"""Снимки API очереди в отдельной in-memory SQLite; TTL-сценарий с тестовыми часами."""
from datetime import datetime, timedelta
import json
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.core.config import ROOT
from app.main import create_app
from app.ml.query_parser import FixtureQueryParser
from app.storage.db import create_db
from scripts.seed_demo import seed


def export_contract():
    engine = create_db('sqlite://')
    try:
        seed(engine)
        with TestClient(create_app(engine=engine, parser=FixtureQueryParser())) as client:
            def call(method, path, payload=None):
                response = client.request(method, path, json=payload)
                response.raise_for_status()
                return response.json()
            hotel = call('GET', '/api/hotels')[0]
            request = {'hotel_id': hotel['id'], 'feature_key': 'sea_view'}
            question = call('POST', '/api/hotelier/questions', request)
            states = {'open': question}
            def snapshot():
                return call('GET', '/api/hotelier/questions?hotel_id=' + hotel['id'])[0]
            def reply(text):
                return call('POST', f'/api/hotelier/questions/{question["id"]}/answer', {'text': text})
            def confirm(answer, accept=True):
                return call('POST', f'/api/hotelier/answers/{answer["id"]}/confirm', {'accept': accept})
            first = reply('В номере 301 есть вид на море.')
            states['pending'] = snapshot()
            positive = confirm(first)
            states['answered'] = snapshot()
            confirm(reply('В номере 301 нет вида на море.'))
            states['reopened'] = snapshot()
            conflict = call('GET', '/api/hotelier/conflicts')[0]
            call('POST', f'/api/hotelier/conflicts/{conflict["id"]}/resolve', {
                'selected_observation_id': positive['observation_ids'][0], 'reason': 'Учебное уточнение'})
            states['resolved'] = snapshot()
            unclear = reply('Возможно, в номере 302 вид на море.')
            states['unparsed'] = snapshot()
            confirm(unclear, False)
            states['rejected'] = snapshot()
            confirm(reply('В номере 302 есть вид на море.'))
            future = datetime.fromisoformat(snapshot()['updated_at']) + timedelta(days=91)
            with patch('app.storage.repository.now_utc', return_value=future):
                states['stale'] = snapshot()
            return {'fixture_only': True, 'ttl_scenario_uses_simulated_clock': True,
                    'description': 'Снимки настоящего API с симулированными ответами; не реальные свойства номера.',
                    'question_request': request, 'question_states': states}
    finally:
        engine.dispose()


def main():
    target = ROOT / 'docs/examples/question_integration_fixture.json'
    target.write_text(json.dumps(export_contract(), ensure_ascii=False, indent=2) + '\n')
    print(target)


if __name__ == '__main__':
    main()
