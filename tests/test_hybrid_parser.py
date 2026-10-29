"""Гибридный разбор и защита от чисел, которых нет в запросе."""
import pytest

from app.ml.prompts import EXTRA_EXAMPLES, query_features
from app.ml.query_parser import (HybridQueryParser, ParserError, drop_invented_numbers,
                                 llm_schema, mentioned_numbers)
from app.schemas.query import ParsedHotelQuery


class FakeLLM:
    client = None

    def __init__(self, answer=None):
        self.answer, self.calls = answer, []

    def parse(self, text):
        self.calls.append(text)
        if self.answer is None:
            raise ParserError('нет модели')
        return ParsedHotelQuery.model_validate(self.answer | {'original_text': text})


def test_rules_answer_is_final_when_everything_matched():
    llm = FakeLLM({'soft_preferences': [{'feature_key': 'sea_view', 'desired': True, 'scope': 'room'}]})
    parser = HybridQueryParser(llm=llm)
    parsed = parser.parse('Хочу тихий отель подальше от баров')
    assert llm.calls == [] and parser.last_source == 'rules'
    assert {p.feature_key for p in parsed.soft_preferences} >= {'quietness_proxy', 'nightlife_distance_m'}


def test_unmatched_words_go_to_llm():
    answer = {'soft_preferences': [{'feature_key': 'beach_route_climb_m', 'desired': 'near', 'scope': 'hotel'}]}
    llm = FakeLLM(answer)
    parser = HybridQueryParser(llm=llm)
    parsed = parser.parse('Бабушке трудно карабкаться, хотим путь к воде поровнее')
    assert llm.calls and parser.last_source == 'llm'
    assert parsed.soft_preferences[0].feature_key == 'beach_route_climb_m'


def test_llm_failure_falls_back_to_rules_without_hiding_unmatched_words():
    parser = HybridQueryParser(llm=FakeLLM(None))
    parsed = parser.parse('Бабушке трудно карабкаться, хотим путь к воде поровнее')
    assert parser.last_source == 'rules_fallback'
    assert parsed.ignored_terms  # гость увидит, что учтено не всё


@pytest.mark.parametrize('text,expected', [
    ('До пляжа не более 0,4 км', {0.4, 400.0}),
    ('максимум полкилометра', {500.0}),
    ('не дальше двух километров', {2.0, 2000.0}),
    ('пять минут пешком', {5.0, 400.0}),
])
def test_mentioned_numbers_cover_units_and_words(text, expected):
    assert expected <= mentioned_numbers(text)


def test_invented_limit_is_dropped_and_real_one_kept():
    parsed = ParsedHotelQuery.model_validate({
        'hard_constraints': [
            {'feature_key': 'walking_distance_to_beach_m', 'operator': '<=', 'value': 500, 'unit': 'm'},
            {'feature_key': 'nightlife_distance_m', 'operator': '>=', 'value': 300, 'unit': 'm'},
            {'feature_key': 'sea_view', 'operator': '=', 'value': True, 'scope': 'room'}],
        'soft_preferences': [{'feature_key': 'walking_distance_to_beach_m', 'desired': 'near',
                              'utility': {'kind': 'lower', 'ideal_max': 500, 'tolerance': 200}}]})
    result = drop_invented_numbers(parsed, 'Бары не ближе 300 м, обязательно вид на море, пляж поближе')
    assert [c.feature_key for c in result.hard_constraints] == ['nightlife_distance_m', 'sea_view']
    assert result.soft_preferences[0].utility is None and result.soft_preferences[0].desired == 'near'


def test_prompt_examples_follow_contract_and_only_query_features():
    allowed = set(query_features())
    assert set(llm_schema()['$defs']['HardConstraint']['properties']['feature_key']['enum']) == allowed
    assert 'aircraft_noise_exposure' not in allowed and 'sea_view_min_floor' not in allowed
    for text, answer in EXTRA_EXAMPLES:
        parsed = ParsedHotelQuery.model_validate(answer())
        keys = {c.feature_key for c in parsed.hard_constraints} | {p.feature_key for p in parsed.soft_preferences}
        assert keys <= allowed, text


def test_unmatched_words_stay_visible_when_llm_adds_nothing():
    """«ХАЧУ …, тихий отель» — LLM ничего нового не нашла, «не учтено» не пропадает."""
    rules = HybridQueryParser(llm=FakeLLM({})).offline.parse('Хочу абракадабру, тихий отель')
    assert rules.ignored_terms
    parser = HybridQueryParser(llm=FakeLLM({}))
    parsed = parser.parse('Хочу абракадабру, тихий отель')
    assert parser.last_source == 'llm' and parsed.ignored_terms == rules.ignored_terms
    answer = {'soft_preferences': [{'feature_key': 'sea_view', 'desired': True, 'scope': 'room'}]}
    assert HybridQueryParser(llm=FakeLLM(answer)).parse('Хочу абракадабру, тихий отель').ignored_terms == []
