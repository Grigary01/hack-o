"""Снимки HTTP-контракта для frontend/ML; модель явно заменена fixture/stub."""
import json
from fastapi.testclient import TestClient
from app.core.config import ROOT
from app.core.errors import ReplyParserUnavailable
from app.hotelier.reply_parser import FixtureReplyParser
from app.main import create_app
from app.ml.query_parser import FixtureQueryParser
from app.schemas.hotelier import ReplyExtraction
from app.storage.db import create_db
from scripts.seed_demo import seed


class UnavailableStub:
    mode = 'stub_unavailable'

    def parse(self, *, feature_key, text):
        raise ReplyParserUnavailable('Учебная ошибка: ML-сервис недоступен; факты не сохранены.')


class InvalidStub:
    mode = 'stub_invalid'

    def parse(self, *, feature_key, text):
        return {'claims': [{'room_number': '999', 'feature_key': 'soundproofing',
                            'value': True, 'quote': text}], 'unparsed': []}


def export_contract():
    engine = create_db('sqlite://')
    try:
        seed(engine)
        result = {'fixture_only': True, 'real_model_used': False,
                  'reply_extraction_schema': ReplyExtraction.model_json_schema()}
        with TestClient(create_app(engine=engine, parser=FixtureQueryParser(), reply_parser=FixtureReplyParser())) as client:
            def call(method, path, payload=None):
                r = client.request(method, path, json=payload)
                r.raise_for_status()
                return r.json()
            hotel = call('GET', '/api/hotels')[0]
            q = call('POST', '/api/hotelier/questions', {'hotel_id': hotel['id'], 'feature_key': 'sea_view'})
            result['question'] = q
            result['valid_request'] = {'text': '301: море видно. 302: окна во двор.'}
            result['pending_answer'] = call('POST', f'/api/hotelier/questions/{q["id"]}/answer', result['valid_request'])
            aid = result['pending_answer']['id']
            result['confirmation'] = call('POST', f'/api/hotelier/answers/{aid}/confirm', {'accept': True})
            result['ambiguous_request'] = {'text': 'В номере 301 вид на море только зимой.'}
            result['ambiguous_answer'] = call('POST', f'/api/hotelier/questions/{q["id"]}/answer', result['ambiguous_request'])
            response = client.post(f'/api/hotelier/answers/{result["ambiguous_answer"]["id"]}/confirm', json={'accept': True})
            assert response.status_code == 422
            result['ambiguous_confirmation'] = {'status_code': response.status_code, 'body': response.json()}
        result['errors'] = {}
        for name, parser in [('unavailable', UnavailableStub()), ('invalid_output', InvalidStub())]:
            with TestClient(create_app(engine=engine, parser=FixtureQueryParser(), reply_parser=parser)) as client:
                response = client.post(f'/api/hotelier/questions/{q["id"]}/answer', json=result['valid_request'])
                assert response.status_code == (503 if name == 'unavailable' else 502)
                result['errors'][name] = {'status_code': response.status_code, 'body': response.json()}
        return result
    finally:
        engine.dispose()


def main():
    target = ROOT / 'docs/examples/reply_integration_fixture.json'
    target.write_text(json.dumps(export_contract(), ensure_ascii=False, indent=2) + '\n')
    print(target)


if __name__ == '__main__':
    main()
