"""Автоматическое сравнение разметки и ответов парсера, без запуска сайта.

python -m scripts.compare_parser --mode ollama --limit 3
python -m scripts.compare_parser --predictions runtime/model_comparison.json --profile local-gemma12b

Косинус здесь дополнительный показатель, а не вероятность правильного ответа.
По умолчанию считаем его на точных структурных признаках без второй нейросети.
--embedding-model включает отдельную embedding-модель Ollama, если она установлена.
"""
import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import time

import httpx
from pydantic import ValidationError

from app.core.config import ROOT, MODEL_CONFIG, settings
from app.ml.query_parser import make_parser, ParserError
from app.schemas.query import ParsedHotelQuery
from scripts.evaluate_parser import fields, dimension


def stable(value):
    """Числа 500 и 500.0 равнозначны; True и 1 остаются разными значениями."""
    if type(value) in (int, float):
        return float(value)
    if isinstance(value, dict):
        return {key: stable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [stable(item) for item in value]
    return value


def token(value):
    return json.dumps(stable(value), ensure_ascii=False, sort_keys=True)


def normalize(raw):
    # Одинаковая Pydantic-схема нормализует единицы и значения по умолчанию.
    # Исходный текст исключаем: он одинаков у эталона и модели и завысил бы cosine.
    result = ParsedHotelQuery.model_validate(raw).model_dump(mode='json')
    result.pop('original_text')
    result.pop('ignored_terms')
    for key in ('hard_constraints', 'soft_preferences', 'unknown_or_ambiguous'):
        result[key] = sorted(result[key], key=token)
    return result


def requirements(query):
    """Одна координата = целое условие, включая обязательность, значение и оператор.

    Нельзя засчитать >=300 и <=700 как >=700 и <=300 только потому, что набор
    отдельных чисел и операторов совпал. Counter также учитывает дубликаты.
    """
    return Counter((kind, token(item)) for kind in ('hard_constraints', 'soft_preferences')
                   for item in query[kind])


def counts(gold, predicted):
    return {'tp': sum((gold & predicted).values()),
            'fp': sum((predicted - gold).values()),
            'fn': sum((gold - predicted).values())}


def prf(values):
    tp, fp, fn = (values[key] for key in ('tp', 'fp', 'fn'))
    # Нет объектов для знаменателя — метрика не определена, а не «100% качества».
    return values | {'precision': tp/(tp+fp) if tp+fp else None,
                     'recall': tp/(tp+fn) if tp+fn else None,
                     'f1': 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}


def cosine_counts(a, b):
    """cos(a,b) = сумма a_i*b_i / (длина a * длина b).

    Координаты — точные признаки, значения — их количества. Обучение не нужно.
    Для пустого вектора угол не определён: возвращаем None и считаем exact отдельно.
    """
    norm = math.sqrt(sum(x*x for x in a.values()) * sum(x*x for x in b.values()))
    return sum(value*b.get(key, 0) for key, value in a.items())/norm if norm else None


def cosine_vectors(a, b):
    if not a or len(a) != len(b) or not all(type(x) in (float, int) and math.isfinite(x) for x in a+b):
        raise ValueError('Embedding-векторы должны иметь одинаковую длину и конечные числа')
    norm = math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return max(-1., min(1., sum(x*y for x, y in zip(a, b))/norm)) if norm else None


def compare(gold, predicted, failed=False):
    """Метрики одной пары. Строгая проверка всегда выполняется независимо от cosine."""
    result = {'exact_match': not failed and token(gold) == token(predicted),
              'hard_exact_match': not failed and token(gold['hard_constraints']) == token(predicted['hard_constraints']),
              'fields': counts(fields(gold), fields(predicted)),
              'requirements': counts(requirements(gold), requirements(predicted)),
              'field_cosine': None if failed else cosine_counts(fields(gold), fields(predicted)),
              'requirement_cosine': None if failed else cosine_counts(requirements(gold), requirements(predicted))}
    for name in ('operators', 'numbers', 'negations'):
        result[name] = counts(dimension(gold, name), dimension(predicted, name))
    return result


def semantic_cosine(client, model, gold, predicted):
    # Сравниваем только извлечённые требования и регион. original_text не передаём!
    # truncate=False запрещает молча обрезать длинный набор требований.
    texts = [token({key: q[key] for key in ('region', 'hard_constraints', 'soft_preferences')})
             for q in (gold, predicted)]
    response = client.post(settings.ollama_url.rstrip('/')+'/api/embed',
                           json={'model': model, 'input': texts, 'truncate': False})
    response.raise_for_status()
    vectors = response.json()['embeddings']
    if not isinstance(vectors, list) or len(vectors) != 2:
        raise ValueError('Ожидались два embedding-вектора')
    return cosine_vectors(*vectors)


def read_predictions(path, profile):
    """Можно повторно оценивать сохранённые ответы, не вызывая Gemma ещё раз.

    JSONL: {text, actual, error?, latency_seconds?}. Также поддерживается JSON
    benchmark_models с profiles/cases. Разметку expected из отчёта не используем.
    """
    if path.suffix == '.jsonl':
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    else:
        raw = json.loads(path.read_text())
        if isinstance(raw, dict) and 'profiles' in raw:
            profiles = [p for p in raw['profiles'] if not profile or p['id'] == profile]
            if len(profiles) != 1:
                raise ValueError('Выберите ровно один существующий --profile')
            rows = profiles[0].get('cases', [])
        else:
            rows = raw if isinstance(raw, list) else raw['cases']
    result = {}
    for row in rows:
        if row['text'] in result:
            raise ValueError('Дубли текста в predictions: нельзя однозначно сопоставить ответы')
        result[row['text']] = row
    return result


def summarize(cases):
    n = len(cases)
    summary = {'queries': n,
               'error_rate': sum(c['error'] is not None for c in cases)/n if n else None,
               'exact_match': sum(c['metrics']['exact_match'] for c in cases)/n if n else None,
               'hard_exact_match': sum(c['metrics']['hard_exact_match'] for c in cases)/n if n else None}
    for name in ('fields', 'requirements', 'operators', 'numbers', 'negations'):
        summary[name] = prf({k: sum(c['metrics'][name][k] for c in cases) for k in ('tp', 'fp', 'fn')})
    for name in ('field_cosine', 'requirement_cosine', 'semantic_cosine'):
        values = [c['metrics'][name] for c in cases if c['metrics'].get(name) is not None]
        summary[name] = {'mean': statistics.mean(values) if values else None, 'evaluated_pairs': len(values)}
    # Ошибки остаются в error_rate/FN; доступное время неудачного вызова тоже учитываем.
    times = sorted(c['latency_seconds'] for c in cases if c['latency_seconds'] is not None)
    summary['latency'] = {'measured_queries': len(times),
                          'median_seconds': statistics.median(times) if times else None,
                          'p95_seconds': times[math.ceil(.95*len(times))-1] if times else None}
    summary['embedding_errors'] = sum(bool(c.get('embedding_error')) for c in cases)
    # Верно ли решено, есть ли в запросе неподдержанное/неясное условие.
    # Текст уточнения не сравниваем: правильных формулировок много.
    labelled = [c for c in cases if 'expected' in c]
    summary['ambiguity_accuracy'] = sum(bool(c['expected']['unknown_or_ambiguous']) == bool((c['actual'] or {}).get('unknown_or_ambiguous'))
                                        for c in labelled)/len(labelled) if labelled else None
    return summary


def by_category(cases):
    """Короткий срез по полю category датасета: где именно парсер ошибается."""
    groups = {}
    for case in cases:
        groups.setdefault(case.get('category') or 'all', []).append(case)
    result = {}
    for name, items in groups.items():
        summary = summarize(items)
        result[name] = {'queries': len(items), 'requirement_f1': summary['requirements']['f1'],
                        'hard_exact_match': summary['hard_exact_match'],
                        'ambiguity_accuracy': summary['ambiguity_accuracy'], 'error_rate': summary['error_rate']}
    return result


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--dataset', type=Path, default=ROOT/'data/evaluation/queries_gold.jsonl')
    source = cli.add_mutually_exclusive_group()
    source.add_argument('--mode', choices=['fixture', 'offline', 'ollama', 'groq', 'hybrid'])
    source.add_argument('--predictions', type=Path)
    cli.add_argument('--profile', help='Профиль из сохранённого benchmark-отчёта')
    cli.add_argument('--split', choices=['demo', 'held_out', 'all'], default='held_out')
    cli.add_argument('--limit', type=int)
    cli.add_argument('--embedding-model', help='Установленная embedding-модель Ollama, например embeddinggemma')
    cli.add_argument('--output', type=Path, default=ROOT/'runtime/parser_comparison.json')
    args = cli.parse_args()
    if args.limit is not None and args.limit <= 0:
        cli.error('--limit должен быть положительным')
    if args.profile and not args.predictions:
        cli.error('--profile используется только вместе с --predictions')
    rows = [json.loads(line) for line in args.dataset.read_text().splitlines() if line.strip()]
    rows = [r for r in rows if args.split == 'all' or r['split'] == args.split]
    if args.limit:
        rows = rows[:args.limit]
    if not rows or len({r['text'] for r in rows}) != len(rows):
        cli.error('Нужны непустые данные с уникальными текстами запросов')
    # Ошибочная разметка — ошибка входных данных, не неудача модели.
    gold = [normalize(row['expected']) for row in rows]
    saved = read_predictions(args.predictions, args.profile) if args.predictions else None
    mode = args.mode or settings.parser_mode
    parser = make_parser(replace(settings, parser_mode=mode)) if saved is None else None
    embed_client = httpx.Client(timeout=settings.parser_timeout_seconds) if args.embedding_model else None
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'running',
              'source': str(args.predictions) if saved is not None else mode,
              'generation_model': (settings.model_name if mode == 'ollama' else settings.groq_model if mode == 'groq' else None) if saved is None else None,
              'profile': args.profile, 'split': args.split,
              'model_config': MODEL_CONFIG.model_dump(), 'embedding_model': args.embedding_model,
              'model_config_sha256': hashlib.sha256((ROOT/'config/models.yaml').read_bytes()).hexdigest(),
              'prompt_sha256': hashlib.sha256((ROOT/'app/ml/prompts.py').read_bytes()).hexdigest(),
              'scorer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'dataset_sha256': hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
              'prediction_sha256': hashlib.sha256(args.predictions.read_bytes()).hexdigest() if args.predictions else None,
              'warning': 'Synthetic default labels require human review. Cosine is not correctness or probability.',
              'cases': []}

    def save():
        report['summary'] = summarize(report['cases'])
        report['by_category'] = by_category(report['cases'])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))

    try:
        for index, (row, expected) in enumerate(zip(rows, gold)):
            error = None
            latency = None
            actual = normalize({})
            started = time.perf_counter()
            try:
                if saved is not None:
                    recorded = saved.get(row['text'])
                    if recorded is None:
                        raise ValueError('missing_prediction: нет ответа на этот запрос')
                    latency = recorded.get('latency_seconds')
                    if latency is not None and (type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0):
                        raise ValueError('Некорректное время в predictions')
                    if recorded.get('error'):
                        raise ValueError(str(recorded['error']))
                    actual = normalize(recorded['actual'])
                else:
                    actual = normalize(parser.parse(row['text']).model_dump(mode='json'))
            except (ParserError, ValidationError, ValueError, KeyError, TypeError) as exc:
                error = f'{type(exc).__name__}: {exc}'
                # Ошибочная метка времени не должна превращаться в NaN в отчёте.
                if latency is not None and (type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0):
                    latency = None
            if saved is None:
                latency = time.perf_counter()-started
            case = {'text': row['text'], 'split': row['split'], 'category': row.get('category'), 'expected': expected,
                    'actual': actual if error is None else None, 'error': error,
                    'latency_seconds': latency, 'metrics': compare(expected, actual, failed=error is not None),
                    # hybrid: кто дал ответ — правила или LLM.
                    'parser_source': getattr(parser, 'last_source', None)}
            if embed_client is not None and error is None and requirements(expected) and requirements(actual):
                try:
                    case['metrics']['semantic_cosine'] = semantic_cosine(embed_client, args.embedding_model, expected, actual)
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                    case['embedding_error'] = f'{type(exc).__name__}: embedding-сравнение не выполнено'
            report['cases'].append(case)
            save()  # Промежуточные ответы сохраняются после каждого запроса.
            print(f'{index+1}/{len(rows)}: {"error" if error else "compared"}', flush=True)
        report['status'] = 'complete'
        save()
    finally:
        if parser is not None and hasattr(parser, 'client'):
            parser.client.close()
        if embed_client is not None:
            embed_client.close()
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))
    fmt = lambda v: '-' if v is None else f'{v:.3f}'
    print(f"{'category':14} {'n':>3} {'reqF1':>6} {'hardEM':>6} {'ambig':>6} {'err':>6}")
    for name, row in report['by_category'].items():
        print(f"{name:14} {row['queries']:>3} {fmt(row['requirement_f1']):>6} {fmt(row['hard_exact_match']):>6} "
              f"{fmt(row['ambiguity_accuracy']):>6} {fmt(row['error_rate']):>6}")
    print(args.output)


if __name__ == '__main__':
    main()
