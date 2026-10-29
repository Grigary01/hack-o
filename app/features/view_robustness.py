"""Закрывают ли вид деревья и соседние дома — по уже посчитанным сценариям viewshed.

Расчёт вида (app/geo/viewshed.py) прогоняется в трёх сценариях: low / base / high.
В них растёт высота деревьев (0 / 0,6 / 1,0 от измеренной по DSM и OSM) и
неизвестных по высоте соседних домов. Сравнивая сценарии, можно честно сказать,
насколько вид из окон зависит от этих препятствий:

- low    — вид одинаков во всех сценариях, нужный этаж почти не меняется;
- medium — вид сужается или нужен этаж заметно выше, но не пропадает;
- high   — в базовом расчёте вид есть, а при высоких деревьях и домах пропадает.

Значение — лучший (наименее рискованный) из видов, которые у здания есть.
Это НЕ съёмка: деревья вплотную к фасаду и сезонная листва не моделируются.
Новых геоданных не нужно: признак выводится из существующего наблюдения.
"""
import hashlib
import json
from app.features.registry import get_registry
from app.schemas.hotel import Evidence, Observation, Source
from app.storage.repository import now_utc

FEATURE_KEY = 'view_obstruction_risk'
RISK_ORDER = ['low', 'medium', 'high']
FAMILIES = (
    ('sea', 'sea_view_potential', 'sea_view_min_floor', 'Море'),
    ('sunset', 'sunset_view_potential', 'sunset_view_min_floor', 'Закат'),
    ('mountain', 'mountain_view_potential', 'mountain_view_min_floor', 'Горы'),
)


def family_risk(scenarios: dict, potential: str, min_floor: str):
    """Риск для одного вида или None, если вида нет даже в базовом расчёте."""
    low, base, high = (scenarios[name].get(potential) for name in ('low', 'base', 'high'))
    if base in (None, 'none'):
        return None
    floors = [scenarios[name].get(min_floor) for name in ('low', 'base', 'high')]
    if high == 'none':
        return 'high', floors
    floor_shift = (floors[2] - floors[0]) if None not in (floors[0], floors[2]) else 0
    if low == base == high and floor_shift <= 1:
        return 'low', floors
    return 'medium', floors


def describe_family(label, definition, scenarios, potential, risk, floors):
    base = definition.display(scenarios['base'][potential])
    high = definition.display(scenarios['high'][potential])
    if risk == 'high':
        return f'{label}: {base} по базовому расчёту, но при высоких деревьях и домах вида нет'
    if risk == 'low':
        return f'{label}: {base} во всех сценариях высоты деревьев и домов'
    floor_note = ''
    if floors[0] is not None and floors[2] is not None and floors[2] > floors[0]:
        floor_note = f', нужен этаж выше: с {floors[2]}-го вместо {floors[0]}-го'
    return f'{label}: {base} по базовому расчёту, при высоких деревьях — {high}{floor_note}'


def compute(repo, hotel_id: str) -> Observation:
    registry = get_registry()
    definition = registry.get(FEATURE_KEY)
    sources = [o for o in repo.observations(hotel_id, 'sea_view_potential')
               if isinstance(o.evidence.details, dict) and o.evidence.details.get('scenarios')]
    now = now_utc()
    if not sources:
        raise ValueError('Нет расчёта вида со сценариями — признак вывести не из чего')
    source = max(sources, key=lambda o: o.collected_at)
    scenarios = source.evidence.details['scenarios']
    families, lines = {}, []
    for key, potential, min_floor, label in FAMILIES:
        result = family_risk(scenarios, potential, min_floor)
        if result is None:
            continue
        risk, floors = result
        families[key] = {'risk': risk, 'low': scenarios['low'].get(potential), 'base': scenarios['base'].get(potential),
                         'high': scenarios['high'].get(potential), 'min_floor': floors}
        lines.append(describe_family(label, registry.get(potential), scenarios, potential, risk, floors))
    value = min((f['risk'] for f in families.values()), key=RISK_ORDER.index) if families else None
    explanation = ('; '.join(lines) + '.') if lines else 'Вида на море, закат или горы нет ни в одном сценарии — закрывать нечего.'
    details = {'explanation': explanation, 'families': families, 'source_observation_id': source.id,
               'method_note': 'Сравнение сценариев low/base/high расчёта вида: высота деревьев 0/0,6/1,0 '
                              'от измеренной и неизвестных соседних домов.'}
    digest = hashlib.sha256(json.dumps([hotel_id, FEATURE_KEY, source.id, details], sort_keys=True,
                                       ensure_ascii=False).encode()).hexdigest()
    return Observation(
        id=digest, hotel_id=hotel_id, subject_type='hotel', subject_id=hotel_id, feature_key=FEATURE_KEY,
        value=value, unit=definition.unit, observed_at=source.observed_at, collected_at=now,
        expires_at=source.expires_at, status='estimated' if value is not None else 'unknown',
        confidence_level='low' if value is not None else 'unknown',
        confidence_method=('Выведено из сценариев расчёта вида; кроны по DSM 30 м грубые, '
                           'деревья вплотную к фасаду и листва по сезонам не учтены.'),
        quality_flags=['derived_from_viewshed_scenarios', 'vegetation_from_dsm_30m_coarse',
                       'street_trees_near_facade_not_modeled'],
        evidence=Evidence(source=Source(type='geo_model', name='Расчёт вида: сценарии деревьев и домов',
                                        ref=source.id, url=source.evidence.source.url),
                          method='view_scenario_robustness_v1', details=details))
