"""Сверка расчётного вида на море и авиашума с ручной разметкой из отзывов и описаний.

Это не «точность модели» в строгом смысле: выборка мала, твёрдых отрицаний
почти нет, отзыв относится к одному номеру. Поэтому отчёт разделяет:
- yes: в эталоне море видно хотя бы откуда-то → модель не должна сказать none;
- no_claim: отель и гости о море молчат, видят город → модельное «море видно»
  не опровергнуто, но и не подтверждено (unconfirmed_positive);
- mixed/ambiguous: не оцениваются, только перечисляются;
- этажи: «море с 9-го» согласуется, если расчётный минимальный этаж ≤ 9;
- этажность: эталон «номера на 4-м этаже» против OSM building:levels.
"""
import argparse
import json
from collections import Counter
from pathlib import Path
from app.core.config import ROOT, settings

STRENGTH_ORDER = ['guest_review', 'hotel_room_category', 'hotel_description', 'amenity_list', 'absence']


def strongest(evidence, label):
    """Самый сильный тип доказательства, поддерживающий именно эту метку."""
    if label == 'no_claim':
        return 'absence'
    kinds = {e['source_type'] for e in evidence if label in e['supports']}
    return next((k for k in STRENGTH_ORDER if k in kinds), None)


def evaluate(gold, features):
    model, aircraft = {}, {}
    for f in features:
        if f['feature_key'] == 'aircraft_noise_exposure':
            aircraft[f['hotel_id']] = {'exposure': f['value'], 'nearest': f['evidence']['details'].get('nearest')}
        if f['feature_key'] in ('sea_view_potential', 'sea_view_min_floor'):
            entry = model.setdefault(f['hotel_id'], {'details': f['evidence']['details']})
            entry[f['feature_key']] = f['value']
            entry['confidence_level'] = f['confidence_level']
    rows, conflicts, unscored = [], [], []
    for hotel in gold['hotels']:
        label = hotel['labels'].get('sea_view')
        predicted = model.get(hotel['hotel_id'])
        if predicted is None or hotel['identity']['status'] not in ('matched', 'probable'):
            continue
        details = predicted['details']
        levels = hotel.get('levels_evidence')
        if levels and details.get('levels') is not None and levels['min_levels'] > details['levels']:
            conflicts.append({'hotel_id': hotel['hotel_id'], 'name': hotel['name'], 'kind': 'building_levels',
                              'osm_levels': details['levels'], 'osm_levels_source': details.get('levels_source'),
                              'evidence_min_levels': levels['min_levels'], 'url': levels['url'],
                              'action': 'спросить отельера об этажности и пересчитать вид для верхних этажей'})
        if label is None:
            continue
        potential, min_floor = predicted.get('sea_view_potential'), predicted.get('sea_view_min_floor')
        if label in ('mixed', 'ambiguous'):
            unscored.append({'hotel_id': hotel['hotel_id'], 'name': hotel['name'], 'label': label,
                             'model': potential, 'model_min_floor': min_floor})
            continue
        if label == 'yes':
            outcome = 'agree' if potential not in (None, 'none') else 'disagree'
        else:  # no_claim
            outcome = 'agree' if potential == 'none' else 'unconfirmed_positive'
        floors = []
        for fe in hotel.get('floor_evidence', []):
            ok = (min_floor is not None and fe['floor'] >= min_floor) if fe['sea_view'] else None
            floors.append({'floor': fe['floor'], 'sea_view': fe['sea_view'], 'consistent': ok})
        rows.append({'hotel_id': hotel['hotel_id'], 'name': hotel['name'], 'label': label,
                     'evidence': strongest(hotel['evidence'], 'sea_view=yes' if label == 'yes' else label),
                     'identity': hotel['identity']['status'], 'model': potential, 'model_min_floor': min_floor,
                     'confidence_level': predicted['confidence_level'], 'outcome': outcome, 'floors': floors})
    noise_rows = []
    for hotel in gold['hotels']:
        if hotel['labels'].get('aircraft_noise') == 'reported' and hotel['hotel_id'] in aircraft:
            predicted = aircraft[hotel['hotel_id']]
            noise_rows.append({'hotel_id': hotel['hotel_id'], 'name': hotel['name'], 'label': 'reported',
                               'model': predicted['exposure'],
                               'slant_m': (predicted['nearest'] or {}).get('slant_m'),
                               'outcome': 'agree' if predicted['exposure'] in ('medium', 'high') else 'disagree'})
    positives = [r for r in rows if r['label'] == 'yes']
    floor_checks = [f for r in rows for f in r['floors'] if f['consistent'] is not None]
    return {
        'gold_hotels': len(gold['hotels']), 'scored': len(rows),
        'outcomes': dict(Counter(r['outcome'] for r in rows)),
        # Доля подтверждённых «море видно», которые модель тоже нашла.
        'recall_on_confirmed_sea_view': (sum(r['outcome'] == 'agree' for r in positives) / len(positives)
                                         if positives else None),
        'recall_on_guest_reviews_only': (lambda g: sum(r['outcome'] == 'agree' for r in g) / len(g) if g else None)(
            [r for r in positives if r['evidence'] == 'guest_review']),
        'precision': None,
        'precision_note': 'Не измеряется: нет надёжных отрицательных примеров (отсутствие упоминания ≠ нет вида).',
        'floor_checks': {'total': len(floor_checks), 'consistent': sum(f['consistent'] for f in floor_checks)},
        'rows': rows, 'unscored': unscored, 'source_conflicts': conflicts,
        'aircraft_noise': {'rows': noise_rows,
                           'agree': sum(r['outcome'] == 'agree' for r in noise_rows), 'total': len(noise_rows)},
        'note': 'Малая ручная выборка; это проверка на грубые ошибки и источник конфликтов, не оценка точности.',
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gold', type=Path, default=ROOT/'data/evaluation/view_gold.json')
    parser.add_argument('--output', type=Path, default=ROOT/'data/evaluation/viewshed_metrics.json')
    args = parser.parse_args()
    report = evaluate(json.loads(args.gold.read_text()), json.loads((settings.demo_dir/'features.json').read_text()))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k not in ('rows',)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
