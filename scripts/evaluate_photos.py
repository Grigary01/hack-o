"""Сверка расчётов вида с ручными наблюдениями по фото (data/evaluation/photo_checks.json).

Проверки:
- levels: сколько этажей считала модель против сосчитанных на фасаде;
- sea (снято с верхнего этажа): модель должна видеть море хотя бы откуда-то;
- sunset_over_sea: модель должна найти месяцы, когда солнце садится в море;
- mountains / snow_peaks: модель видит горы; для снежных вершин — видимые высоты ≥ 2000 м;
- trees_block_view: деревья заслоняют вид — модель должна их учитывать (флаг ограничения иначе).
"""
import argparse
import json
from pathlib import Path
from app.core.config import ROOT, settings

SNOW_LINE_M = 2000


def check(observation, model):
    """Список (проверка, результат True/False, пояснение) для одного фото."""
    sea, sunset, mountain = model['sea_view_potential'], model['sunset_view_potential'], model['mountain_view_potential']
    d = sea['evidence']['details']
    base = d.get('base', {})
    results = []
    if observation.get('levels') is not None:
        expected, certainty = observation['levels'], observation['levels_certainty']
        got = d.get('levels')
        if d.get('levels_source') == 'photo_verified':
            # Этажность взята из этого же фото — это исправление входных данных, а не проверка.
            results.append(('levels_fixed_from_photo', True, f'исправлено по фото: {got} этажа (OSM ошибался)'))
        else:
            ok = got >= expected if certainty == 'at_least' else abs(got - expected) <= (1 if certainty == 'approx' else 0)
            results.append(('levels', ok, f'модель {got} ({d.get("levels_source")}), фото {expected} ({certainty})'))
    if observation.get('sea') and observation.get('floor_hint') == 'upper':
        results.append(('sea_upper_floor', sea['value'] not in (None, 'none'), f'модель: {sea["value"]}'))
    if observation.get('sunset_over_sea'):
        months = base.get('best_sunset', {}).get('sunset_over_sea_months', [])
        results.append(('sunset_over_sea', bool(months), f'месяцев заката в море по модели: {len(months)}'))
    if observation.get('mountains'):
        results.append(('mountains', mountain['value'] not in (None, 'none'), f'модель: {mountain["value"]}'))
    if observation.get('snow_peaks'):
        peak = mountain['evidence']['details'].get('base', {}).get('best_mountain', {}).get('mountain_peak_m') or 0
        results.append(('snow_peaks_height', peak >= SNOW_LINE_M, f'видимая высота по модели ≈ {peak} м'))
    if observation.get('trees_block_view'):
        share = base.get('vegetation_horizon_share_floor1')
        modeled = share is not None and share >= .05
        results.append(('trees_on_horizon', modeled, 'деревья не моделируются' if share is None else
                        f'по модели кроны закрывают {share*100:.0f}% горизонта 1-го этажа'))
    return results


def evaluate(photos, features):
    model = {}
    for f in features:
        model.setdefault(f['hotel_id'], {})[f['feature_key']] = f
    rows, totals = [], {}
    for observation in photos['observations']:
        facts = model.get(observation['hotel_id'], {})
        if 'sea_view_potential' not in facts or facts['sea_view_potential']['value'] is None:
            continue
        for name, ok, note in check(observation, facts):
            totals.setdefault(name, [0, 0])
            totals[name][0] += ok
            totals[name][1] += 1
            rows.append({'hotel': observation['name'], 'check': name, 'ok': ok, 'note': note, 'url': observation['url']})
    tests = {k: v for k, v in totals.items() if k != 'levels_fixed_from_photo'}
    return {'checks': {k: {'passed': v[0], 'total': v[1]} for k, v in totals.items()},
            'passed': sum(v[0] for v in tests.values()), 'total': sum(v[1] for v in tests.values()),
            'fixed_inputs': totals.get('levels_fixed_from_photo', [0, 0])[1],
            'rows': rows, 'note': 'Ручная проверка по фото, малая выборка; это поиск системных ошибок, не оценка точности.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'data/evaluation/photo_metrics.json')
    args = parser.parse_args()
    photos = json.loads((ROOT / 'data/evaluation/photo_checks.json').read_text())
    report = evaluate(photos, json.loads((settings.demo_dir / 'features.json').read_text()))
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, ensure_ascii=False, indent=2))
    for row in report['rows']:
        if not row['ok']:
            print('✗', row['hotel'], row['check'], '—', row['note'])


if __name__ == '__main__':
    main()
