from dataclasses import replace
import json
import httpx
import pytest
from app.core.config import settings
from app.ml.query_parser import GroqQueryParser,FixtureQueryParser,ParserError
from scripts.benchmark_models import preflight,evaluate_cases


def test_groq_same_schema_and_no_hotel_database_in_payload():
    expected=FixtureQueryParser().parse('Нужен номер без вида на море')
    def handler(request):
        assert request.headers['Authorization']=='Bearer test-secret'
        body=json.loads(request.content)
        assert body['model']=='openai/gpt-oss-120b'
        assert body['response_format']['json_schema']['schema']['$defs']['HardConstraint']['properties']['feature_key']['enum']
        assert body['messages'][-1]['role']=='user'
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':expected.model_dump_json()}}]})
    parser=GroqQueryParser(replace(settings,groq_api_key='test-secret'),httpx.Client(transport=httpx.MockTransport(handler)))
    assert parser.parse('Нужен номер без вида на море').hard_constraints[0].value is False


def test_missing_key_never_makes_request():
    def handler(_): raise AssertionError('Network must not be used')
    parser=GroqQueryParser(replace(settings,groq_api_key=''),httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ParserError,match='GROQ_API_KEY'): parser.parse('test')


@pytest.mark.parametrize('status',[401,429,503])
def test_http_failure_no_fallback_or_retry_or_secret_in_error(status):
    calls=[]
    def handler(_):
        calls.append(1)
        return httpx.Response(status,json={'error':'not in output test-secret'})
    parser=GroqQueryParser(replace(settings,groq_api_key='test-secret'),httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ParserError) as exc: parser.parse('test')
    assert len(calls)==1 and 'test-secret' not in str(exc.value)


def test_bad_json_bounded_and_preflight_missing_model():
    calls=[]
    def handler(_):
        calls.append(1)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'broken'}}]})
    parser=GroqQueryParser(replace(settings,groq_api_key='x'),httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ParserError): parser.parse('test')
    assert len(calls)==2
    client=httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'data':[]})))
    assert not preflight({'mode':'groq','model':'missing'},replace(settings,groq_api_key='x'),client)['ready']


def test_benchmark_reports_actual_measurement_and_failures():
    fixture=FixtureQueryParser()
    text=fixture.examples[0]['text']
    rows=[{'text':text,'split':'demo','expected':fixture.examples[0]['expected']}]
    result=evaluate_cases({'id':'synthetic-test'},rows,fixture)
    assert result['metrics']['demo']['exact_match']==1
    assert result['latency_median_seconds']>=0 and result['errors']==0
    class Broken:
        def parse(self,text): raise ParserError('synthetic failure')
    result=evaluate_cases({'id':'synthetic-test'},rows,Broken())
    assert result['errors']==1 and result['metrics']['demo']['covered']==0
