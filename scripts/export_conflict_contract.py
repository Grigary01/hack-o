"""Выгружает fixture для frontend/ML из настоящего API с отдельной in-memory БД.

python -m scripts.export_conflict_contract
Все ответы отельера — симуляция; настоящий LLM и рабочая база не используются.
"""
import json
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
            question = call('POST', '/api/hotelier/questions', {'hotel_id': hotel['id'], 'feature_key': 'sea_view'})
            ids = []
            for text in ('В номере 301 есть вид на море.', 'В номере 301 нет вида на море.'):
                answer = call('POST', f'/api/hotelier/questions/{question["id"]}/answer', {'text': text})
                result = call('POST', f'/api/hotelier/answers/{answer["id"]}/confirm', {'accept': True})
                ids.extend(result['observation_ids'])
            conflict = call('GET', '/api/hotelier/conflicts')[0]
            request = {'selected_observation_id': ids[0], 'reason': 'Учебный пример: выбран первый ответ о номере 301'}
            response = call('POST', f'/api/hotelier/conflicts/{conflict["id"]}/resolve', request)
            return {
                'fixture_only': True,
                'description': 'Симулированные ответы. Снимок API для разработки frontend/ML, не сведения о реальном номере.',
                'hotel': hotel,
                'parsed_query': call('POST', '/api/parse-query', {'text': 'Нужен номер обязательно с видом на море'}),
                'open_conflict': conflict,
                'resolution_request': request,
                'resolution_response': response,
                'resolved_conflict': call('GET', '/api/hotelier/conflicts')[0],
            }
    finally:
        engine.dispose()


def main():
    target = ROOT / 'docs/examples/conflict_integration_fixture.json'
    target.write_text(json.dumps(export_contract(), ensure_ascii=False, indent=2) + '\n')
    print(target)


if __name__ == '__main__':
    main()
