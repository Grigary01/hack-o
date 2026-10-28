"""Целостность размеченных наборов: разметка должна проходить контракт и не утекать в промпт."""
import json

import pytest

from app.core.config import ROOT
from app.features.registry import get_registry
from app.ml.query_parser import OfflineQueryParser, normalize, llm_schema
from app.ml.prompts import query_messages
from app.schemas.query import ParsedHotelQuery
from scripts import build_parser_eval_sets
from scripts.compare_parser import compare, normalize as normalize_query, prf

DATASETS = ['queries_gold.jsonl', 'parser_stress_2026-10-29.jsonl',
            'parser_eval_v2_2026-10-29.jsonl', 'parser_test_v3_2026-10-29.jsonl']


def rows(name):
    return [json.loads(line) for line in (ROOT / 'data/evaluation' / name).read_text().splitlines() if line.strip()]


@pytest.mark.parametrize('name', DATASETS)
def test_labels_follow_contract_and_registry(name):
    data = rows(name)
    assert len({normalize(r['text']) for r in data}) == len(data), 'дубли текста'
    registry = get_registry()
    for row in data:
        raw = row['expected']
        for item in raw['soft_preferences']:
            if item.get('weight_source', 'default') == 'default':
                # Pydantic молча заменит вес на default_weight — ловим опечатку в разметке.
                assert item['importance'] == registry.get(item['feature_key']).default_weight, row['text']
        ParsedHotelQuery.model_validate(raw)
        assert bool(raw['unknown_or_ambiguous']) == (raw['clarification_question'] is not None), row['text']


def test_held_out_texts_are_not_in_fixtures_or_prompt():
    fixtures = {normalize(e['text']) for e in json.loads((ROOT / 'data/demo/query_fixtures.json').read_text())}
    messages = query_messages('новый запрос', llm_schema())
    prompt_inputs = {normalize(m['content']) for m in messages[1:-1] if m['role'] == 'user'}
    for name in DATASETS:
        for row in rows(name):
            if row['split'] == 'held_out':
                assert normalize(row['text']) not in fixtures | prompt_inputs, row['text']


@pytest.mark.parametrize('name', list(build_parser_eval_sets.SETS))
def test_eval_file_is_frozen_output_of_builder(name):
    """Разметку меняют только через builder, а не правкой JSONL после просмотра ответов."""
    prefix, cases = build_parser_eval_sets.SETS[name]
    assert (ROOT / 'data/evaluation' / name).read_text() == build_parser_eval_sets.build(prefix, cases)


@pytest.mark.parametrize('name,floor', [('parser_eval_v2_2026-10-29.jsonl', .84),
                                        ('parser_test_v3_2026-10-29.jsonl', .86)])
def test_rules_parser_does_not_regress(name, floor):
    parser = OfflineQueryParser()
    totals = {'tp': 0, 'fp': 0, 'fn': 0}
    for row in rows(name):
        metrics = compare(normalize_query(row['expected']), normalize_query(parser.parse(row['text']).model_dump(mode='json')))
        for key in totals:
            totals[key] += metrics['requirements'][key]
    # 29.10.2026: v2 0.847, v3 0.865 (до починки правил 0.805/0.826). Падение — регрессия.
    assert prf(totals)['f1'] >= floor
