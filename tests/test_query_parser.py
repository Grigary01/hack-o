import json
import httpx
import pytest
from pydantic import ValidationError
from app.core.config import ROOT
from app.ml.query_parser import FixtureQueryParser, OllamaQueryParser, ParserError
from app.schemas.query import HardConstraint, ParsedHotelQuery, SoftPreference


def test_fixture_units_negations_and_unknown():
    parser=FixtureQueryParser()
    assert parser.parse('До пляжа не более 0.5 км пешком').hard_constraints[0].value==500
    assert parser.parse('Нужен номер без вида на море').hard_constraints[0].value is False
    assert parser.parse('Не хочу рядом с барами').soft_preferences[0].desired=='far'
    vague=parser.parse('Хочу отель недалеко от моря')
    assert not vague.hard_constraints and vague.soft_preferences[0].desired=='near'
    assert parser.parse('Отель с драконом').unknown_or_ambiguous


def test_kilometers_and_strict_contract():
    c=HardConstraint(feature_key='walking_distance_to_beach_m',operator='<=',value=.5,unit='km')
    assert (c.value,c.unit)==(500,'m')
    for patch in [{'value':True},{'value':-2},{'unit':'minutes'},{'scope':'room'},{'feature_key':'invented'}]:
        with pytest.raises(ValidationError):
            HardConstraint.model_validate(c.model_dump()|patch)
    with pytest.raises(ValidationError):
        HardConstraint(feature_key='sea_view',operator='>',value=True,scope='room')
    with pytest.raises(ValidationError):
        ParsedHotelQuery.model_validate_json('```json {} ```')


def test_gold_is_valid_and_contains_held_out():
    rows=[json.loads(line) for line in (ROOT/'data/evaluation/queries_gold.jsonl').read_text().splitlines()]
    assert 40<=len(rows)<=60
    assert len({r['text'] for r in rows})==len(rows)
    assert sum(r['split']=='held_out' for r in rows)==32
    for row in rows:
        ParsedHotelQuery.model_validate(row['expected'])


def test_ollama_uses_schema_and_options():
    expected=FixtureQueryParser().parse('Нужен номер без вида на море')
    calls=[]
    def handle(request):
        body=json.loads(request.content)
        calls.append(body)
        assert body['format']['$defs']['HardConstraint']['properties']['feature_key']['enum']
        assert body['options']['temperature']==0
        assert len(body['messages'])>=12
        return httpx.Response(200,json={'message':{'content':expected.model_dump_json()}})
    parser=OllamaQueryParser(client=httpx.Client(transport=httpx.MockTransport(handle)))
    assert parser.parse('Нужен номер без вида на море').hard_constraints[0].value is False
    assert len(calls)==1


@pytest.mark.parametrize('payload', [
    {'message': {'content': '{not json}'}},
    {'message': None},
    [],
])
def test_invalid_ollama_json_is_bounded_error(payload):
    calls=[]
    def handle(request):
        calls.append(1)
        return httpx.Response(200,json=payload)
    parser=OllamaQueryParser(client=httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(ParserError):
        parser.parse('test')
    assert len(calls)==2
