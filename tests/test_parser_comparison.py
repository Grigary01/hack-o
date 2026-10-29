"""Регрессии метрик: отрицания, границы интервалов, пропуски и дубликаты."""
import json
import math

import httpx
import pytest

from scripts.compare_parser import (normalize, compare, cosine_counts, cosine_vectors,
                                    read_predictions, semantic_cosine, summarize)


def distance(operator, value):
    return {'feature_key': 'walking_distance_to_beach_m', 'operator': operator,
            'value': value, 'unit': 'm', 'scope': 'hotel'}


def test_operator_flip_cannot_pass_despite_high_field_cosine():
    gold = normalize({'hard_constraints': [distance('<=', 500)]})
    actual = normalize({'hard_constraints': [distance('>=', 500)]})
    result = compare(gold, actual)
    assert not result['exact_match'] and not result['hard_exact_match']
    assert result['field_cosine'] > .5
    assert result['requirement_cosine'] == 0
    assert result['requirements'] == {'tp': 0, 'fp': 1, 'fn': 1}
    assert result['operators'] == {'tp': 0, 'fp': 1, 'fn': 1}


def test_complete_constraints_preserve_operator_number_pairing():
    gold = normalize({'hard_constraints': [distance('>=', 300), distance('<=', 700)]})
    actual = normalize({'hard_constraints': [distance('>=', 700), distance('<=', 300)]})
    result = compare(gold, actual)
    # Даже полное совпадение набора отдельных полей не доказывает правильности.
    assert result['field_cosine'] == pytest.approx(1)
    assert result['requirement_cosine'] == 0
    assert not result['hard_exact_match']


def test_order_units_and_echo_do_not_change_structured_comparison():
    one, two = distance('>=', 300), distance('<=', 700)
    gold = normalize({'hard_constraints': [one, two], 'original_text': 'Один текст'})
    actual = normalize({'hard_constraints': [two, one | {'value': .3, 'unit': 'km'}],
                        'original_text': 'Другой текст', 'ignored_terms': ['неважно']})
    assert compare(gold, actual)['exact_match']
    assert compare(gold, actual)['requirement_cosine'] == pytest.approx(1)


def test_boolean_negation_and_duplicates_are_errors():
    yes = {'feature_key': 'sea_view', 'operator': '=', 'value': True, 'scope': 'room'}
    gold = normalize({'hard_constraints': [yes | {'value': False}]})
    assert compare(gold, normalize({'hard_constraints': [yes]}))['negations']['fn'] == 1
    duplicate = normalize({'hard_constraints': [yes, yes]})
    result = compare(normalize({'hard_constraints': [yes]}), duplicate)
    assert result['requirements']['fp'] == 1
    # Cosine не замечает одинаковое масштабирование вектора — ещё одна причина считать F1.
    assert result['requirement_cosine'] == pytest.approx(1)
    assert not result['exact_match']


def test_failed_and_empty_predictions_are_not_perfect_scores():
    gold = normalize({'hard_constraints': [distance('<=', 500)]})
    failed = {'error': 'timeout', 'latency_seconds': 90., 'metrics': compare(gold, normalize({}), failed=True)}
    report = summarize([failed])
    assert report['error_rate'] == 1 and report['requirements']['recall'] == 0
    assert report['field_cosine']['mean'] is None
    assert report['latency']['p95_seconds'] == 90
    assert cosine_counts({}, {}) is None
    assert cosine_vectors([0, 0], [1, 1]) is None
    assert compare(normalize({}), normalize({}))['exact_match']
    with pytest.raises(ValueError):
        cosine_vectors([1, math.nan], [1, 2])


def test_replay_requires_unambiguous_profile_and_unique_queries(tmp_path):
    path = tmp_path/'predictions.json'
    path.write_text(json.dumps({'profiles': [{'id': 'a', 'cases': []}, {'id': 'b', 'cases': []}]}))
    with pytest.raises(ValueError, match='profile'):
        read_predictions(path, None)
    assert read_predictions(path, 'a') == {}
    path.write_text(json.dumps([{'text': 'same'}, {'text': 'same'}]))
    with pytest.raises(ValueError, match='Дубли'):
        read_predictions(path, None)


def test_embedding_compares_requirements_without_shared_original_text():
    gold = normalize({'hard_constraints': [distance('<=', 500)], 'original_text': 'SECRET ORIGINAL'})
    def handle(request):
        body = json.loads(request.content)
        assert request.url.path == '/api/embed'
        assert body['truncate'] is False
        assert len(body['input']) == 2
        assert 'SECRET ORIGINAL' not in request.content.decode()
        assert 'original_text' not in request.content.decode()
        return httpx.Response(200, json={'embeddings': [[1., 0.], [0., 1.]]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        assert semantic_cosine(client, 'embedding-test', gold, gold) == 0
