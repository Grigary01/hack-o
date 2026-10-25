"""Измеряем качество понимания запросов на заранее размеченном наборе.

Запуск: python -m scripts.evaluate_parser --mode fixture (или ollama).
Веса модели здесь НЕ обучаются. Мы сравниваем её ответы с ручным эталоном.
Demo и held-out считаются отдельно: заученный пример не доказывает обобщение.
Подробное объяснение метрик и ограничений: docs/ML_GUIDE.md.
"""
import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import json

from app.core.config import ROOT, settings
from app.ml.query_parser import make_parser, ParserError


def canonical(value) -> str:
    """Превращает значение в стабильный ключ для сравнения полей.

    Числа 500 и 500.0 имеют один смысл. Но bool в Python — подкласс int,
    поэтому здесь проверяем именно type: False НЕ превращается в 0 метров.
    """
    if type(value) in (int, float):
        value = float(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def fields(query) -> Counter:
    """Разбивает hard/soft JSON на атомарные факты для precision/recall.

    Пример: ('hard_constraints', 'walking_distance_to_beach_m', 'value', '500.0').
    Ключ фичи включён в каждый факт: 500 м до пляжа не равно 500 м до баров.
    Counter — мультимножество: лишний дубликат нельзя скрыть обычным set.
    Регион и неоднозначность проверяет exact_match, а не эта полевая метрика.
    """
    values = []
    for kind in ('hard_constraints', 'soft_preferences'):
        for item in query[kind]:
            for name, value in item.items():
                if name != 'feature_key':
                    values.append((kind, item['feature_key'], name, canonical(value)))
    return Counter(values)


def dimension(query, name: str) -> Counter:
    """Дополнительные срезы ошибок, которые особенно опасны для подбора.

    operators: не перепутали ли <= и >=;
    numbers: сохранили ли число после нормализации единиц;
    negations: False («без вида») и far («не рядом с барами»).
    Это ограниченный набор паттернов, не универсальная метрика русского отрицания.
    """
    results = []
    for constraint in query['hard_constraints']:
        key, value = constraint['feature_key'], constraint['value']
        if name == 'operators':
            results.append((key, constraint['operator']))
        if name == 'numbers' and type(value) in (int, float):
            results.append((key, float(value)))
        if name == 'negations' and value is False:
            results.append((key, False))
    for preference in query['soft_preferences']:
        key, desired = preference['feature_key'], preference['desired']
        if name == 'negations' and desired is False:
            results.append((key, False))
        if name == 'negations' and key == 'nightlife_distance_m' and desired == 'far':
            results.append((key, 'far'))
    return Counter(results)


def measure(rows, parser) -> dict:
    """Один проход по одному split. Статистика накапливается по всем полям.

    TP = правильно извлечённое поле; FP = лишнее/неверное; FN = пропущенное.
    Неверное значение даёт и FP для ответа, и FN для отсутствующего эталона.
    """
    exact = tp = fp = fn = covered = 0
    dimensions = {
        name: {'correct': 0, 'expected': 0, 'predicted': 0}
        for name in ('operators', 'numbers', 'negations')
    }
    errors = []
    mismatches = []
    for row in rows:
        expected = row['expected']
        try:
            actual = parser.parse(row['text']).model_dump(mode='json')
        except ParserError as exc:
            # Не выбрасываем неудачу из знаменателя: иначе качество завысится.
            errors.append({'text': row['text'], 'error': str(exc)})
            actual = {
                'hard_constraints': [], 'soft_preferences': [],
                'region': 'unknown', 'unknown_or_ambiguous': ['parser_error'],
            }

        unsupported = 'Запрос вне набора демо-парсера' in actual.get('unknown_or_ambiguous', [])
        parser_failed = actual.get('unknown_or_ambiguous') == ['parser_error']
        covered += not unsupported and not parser_failed
        # Exact match строгий: совпадают весь контракт, регион, clarification,
        # веса и порядок списков. Возможны семантически близкие, но не точные ответы.
        exact += actual == expected
        if actual != expected:
            mismatches.append({'text': row['text'], 'expected': expected, 'actual': actual})

        gold, pred = fields(expected), fields(actual)
        tp += sum((gold & pred).values())
        fp += sum((pred - gold).values())
        fn += sum((gold - pred).values())
        for name in dimensions:
            gold_slice, pred_slice = dimension(expected, name), dimension(actual, name)
            dimensions[name]['correct'] += sum((gold_slice & pred_slice).values())
            dimensions[name]['expected'] += sum(gold_slice.values())
            dimensions[name]['predicted'] += sum(pred_slice.values())

    # Micro-метрики: сначала суммируем поля всех запросов, потом делим.
    # Precision: какая доля выданных полей верна. Recall: сколько нужных нашли.
    # F1 — гармоническое среднее, низкое значение любой из двух метрик его снижает.
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    return {
        'queries': len(rows), 'covered': covered,
        'exact_match': exact / len(rows) if rows else None,
        'field_precision': precision, 'field_recall': recall,
        'field_f1': 2 * precision * recall / (precision + recall) if precision + recall else 0,
        'dimensions': dimensions, 'errors': errors, 'mismatches': mismatches,
    }


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--mode', choices=['fixture', 'ollama'], default=settings.parser_mode)
    mode = args.parse_args().mode
    parser = make_parser(replace(settings, parser_mode=mode))
    path = ROOT / 'data/evaluation/queries_gold.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]

    # Demo совпадает с fixtures; первые 8 demo также входят в few-shot промпт.
    # Held-out не передаётся parser/prompts. Не переносите туда подсмотренные ответы.
    report = {
        'mode': mode, 'model': settings.model_name if mode == 'ollama' else None,
        'measured_at': datetime.now(timezone.utc).isoformat(),
        'note': 'Fixture exact-match на demo — проверка контракта, не качество NLP. Gold авторский, независимая разметка ещё нужна.',
        'demo': measure([row for row in rows if row['split'] == 'demo'], parser),
        'held_out': measure([row for row in rows if row['split'] == 'held_out'], parser),
    }
    # Сохраняем ошибки вместе с метриками: число F1 без примеров трудно улучшать.
    output_path = ROOT / f'data/evaluation/parser_metrics_{mode}.json'
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    # В терминал выводим короткий итог; полные expected/actual остаются в файле.
    summary = {
        split: {key: value for key, value in report[split].items() if key not in ('errors', 'mismatches')}
        for split in ('demo', 'held_out')
    }
    print(json.dumps({'mode': mode, 'report': str(output_path), **summary}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
