"""Экспорт OpenAPI и фактических ответов ядра API из отдельной SQLite, без LLM."""
from dataclasses import replace
import json
from fastapi.testclient import TestClient
from app.core.config import ROOT, settings
from app.main import create_app
from app.ml.query_parser import FixtureQueryParser, GroqQueryParser, ParserError
from app.storage.db import create_db
from scripts.seed_demo import seed


def export_contract():
    engine = create_db('sqlite://')
    try:
        seed(engine)
        api = create_app(engine=engine, parser=FixtureQueryParser())
        examples = {'fixture_only': True, 'real_model_used': False}
        with TestClient(api) as client:
            def call(method, path, payload=None):
                response = client.request(method, path, json=payload)
                response.raise_for_status()
                return response.json()
            examples['health'] = call('GET', '/api/health')
            hotel = call('GET', '/api/hotels')[0]
            q = call('POST', '/api/hotelier/questions', {'hotel_id': hotel['id'], 'feature_key': 'sea_view'})
            examples['question'] = q
            answer = call('POST', f'/api/hotelier/questions/{q["id"]}/answer', {'text': 'В номере 301 есть вид на море.'})
            examples['pending_answer'] = answer
            examples['confirmation'] = call('POST', f'/api/hotelier/answers/{answer["id"]}/confirm', {'accept': True})
            examples['repeat_confirmation'] = call('POST', f'/api/hotelier/answers/{answer["id"]}/confirm', {'accept': True})
            examples['saved_answer'] = call('GET', f'/api/hotelier/answers/{answer["id"]}')
            other = call('POST', f'/api/hotelier/questions/{q["id"]}/answer', {'text': 'В номере 301 нет вида на море.'})
            call('POST', f'/api/hotelier/answers/{other["id"]}/confirm', {'accept': True})
            conflict = call('GET', '/api/hotelier/conflicts')[0]
            examples['open_conflict'] = conflict
            examples['resolution'] = call('POST', f'/api/hotelier/conflicts/{conflict["id"]}/resolve', {
                'selected_observation_id': examples['confirmation']['observation_ids'][0], 'reason': 'Пример контракта API'})
            examples['hotel_detail'] = call('GET', f'/api/hotels/{hotel["id"]}')
            examples['hotel_evidence'] = call('GET', f'/api/hotels/{hotel["id"]}/evidence')
            examples['search'] = call('POST', '/api/search', {'text': 'Нужен номер обязательно с видом на море',
                                                            'include_simulated': True, 'balance': .4})
            examples['errors'] = {}
            for name, method, path, body in [
                ('not_found', 'GET', '/api/hotelier/answers/missing', None),
                ('invalid_request', 'POST', '/api/search', {}),
                ('state_conflict', 'POST', f'/api/hotelier/answers/{answer["id"]}/confirm', {'accept': False}),
            ]:
                response = client.request(method, path, json=body)
                examples['errors'][name] = {'status_code': response.status_code, 'body': response.json()}
        for name, parser, config, path in [
            ('forbidden', FixtureQueryParser(), replace(settings, demo_mode=False), '/api/hotelier/questions'),
            ('service_unavailable', GroqQueryParser(replace(settings, groq_api_key='')), settings, '/api/parse-query'),
        ]:
            with TestClient(create_app(engine=engine, parser=parser, config=config)) as client:
                response = client.get(path) if name == 'forbidden' else client.post(path, json={'text': 'Запрос'})
                examples['errors'][name] = {'status_code': response.status_code, 'body': response.json()}
        class InvalidModel:
            mode = 'stub_invalid'
            def parse(self, text):
                raise ParserError('Учебный пример: модель вернула неверную структуру')
        with TestClient(create_app(engine=engine, parser=InvalidModel())) as client:
            response = client.post('/api/parse-query', json={'text': 'Запрос'})
            examples['errors']['invalid_model_output'] = {'status_code': response.status_code, 'body': response.json()}
        return api.openapi(), examples
    finally:
        engine.dispose()


def main():
    schema, examples = export_contract()
    for name, content in [('backend_api_openapi.json', schema), ('backend_api_examples.json', examples)]:
        target = ROOT / 'docs/examples' / name
        target.write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n')
        print(target)


if __name__ == '__main__':
    main()
