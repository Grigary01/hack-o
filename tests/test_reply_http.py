from dataclasses import replace
import json

import httpx
import pytest

from app.core.config import settings
from app.core.errors import ReplyParserUnavailable, ReplyParserContractError
from app.hotelier.reply_validation import parse_reply
from app.ml.reply_parser import GroqReplyParser, OllamaReplyParser

TEXT = 'В номере 301 есть вид на море.'
EXTRACTION = {'claims': [{'room_number': '301', 'floor': None, 'feature_key': 'sea_view',
                         'value': True, 'quote': 'В номере 301 есть вид на море'}], 'unparsed': []}


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize('provider', ['groq', 'ollama'])
def test_schema_feature_and_payload_are_compatible_and_do_not_include_the_hotel_database(provider):
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body['messages'][-1] == {'role': 'user', 'content': TEXT}
        assert len(body['messages']) == 2
        assert 'osm:' not in json.dumps(body)
        if provider == 'groq':
            assert request.headers['Authorization'] == 'Bearer test-secret'
            schema = body['response_format']['json_schema']['schema']
            response = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(EXTRACTION)}}]}
        else:
            assert body['stream'] is False and body['options']['temperature'] == 0
            schema = body['format']
            response = {'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps(EXTRACTION)}}
        assert schema['$defs']['RoomClaim']['properties']['feature_key']['enum'] == ['sea_view']
        assert schema['properties']['parser_mode']['default'] == provider
        return httpx.Response(200, json=response)
    with client_for(handler) as client:
        parser = (GroqReplyParser if provider == 'groq' else OllamaReplyParser)(
            replace(settings, groq_api_key='test-secret'), client=client)
        result = parse_reply(parser, feature_key='sea_view', text=TEXT)
        assert result.claims[0].value is True and result.parser_mode == provider
        assert not client.is_closed
    assert len(calls) == 1


def test_missing_key_never_makes_network_request():
    def forbidden(_):
        raise AssertionError('Network must not be used')
    with client_for(forbidden) as client:
        parser = GroqReplyParser(replace(settings, groq_api_key=''), client=client)
        with pytest.raises(ReplyParserUnavailable, match='GROQ_API_KEY'):
            parser.parse(feature_key='sea_view', text=TEXT)


@pytest.mark.parametrize('provider', ['groq', 'ollama'])
@pytest.mark.parametrize('status', [401, 429, 503])
def test_http_failures_do_not_retry_fallback_or_leak_upstream_body(provider, status):
    calls = []
    def handler(_):
        calls.append(1)
        return httpx.Response(status, json={'error': 'private test-secret'})
    with client_for(handler) as client:
        parser = (GroqReplyParser if provider == 'groq' else OllamaReplyParser)(
            replace(settings, groq_api_key='test-secret'), client=client)
        with pytest.raises(ReplyParserUnavailable) as exc:
            parser.parse(feature_key='sea_view', text=TEXT)
        assert 'test-secret' not in str(exc.value) and len(calls) == 1


@pytest.mark.parametrize(('provider', 'response'), [
    ('groq', {'choices': []}),
    ('groq', {'choices': [{'finish_reason': 'length', 'message': {'content': json.dumps(EXTRACTION)}}]}),
    ('groq', {'choices': [{'finish_reason': 'stop', 'message': {'content': 'broken'}}]}),
    ('ollama', {'done': False, 'message': {'content': json.dumps(EXTRACTION)}}),
    ('ollama', {'done': True, 'done_reason': 'length', 'message': {'content': json.dumps(EXTRACTION)}}),
    ('ollama', {'done': True, 'message': {'content': 'broken'}}),
])
def test_truncated_or_malformed_response_is_not_treated_as_a_fact(provider, response):
    with client_for(lambda _: httpx.Response(200, json=response)) as client:
        parser = (GroqReplyParser if provider == 'groq' else OllamaReplyParser)(
            replace(settings, groq_api_key='test-secret'), client=client)
        with pytest.raises(ReplyParserContractError):
            parser.parse(feature_key='sea_view', text=TEXT)


def test_schema_rejection_is_502_class_and_not_a_successful_empty_reply():
    with client_for(lambda _: httpx.Response(400, json={'error': 'private body'})) as client:
        with pytest.raises(ReplyParserContractError):
            OllamaReplyParser(client=client).parse(feature_key='sea_view', text=TEXT)
