"""Шум по сторонам здания: есть ли у отеля тихая сторона (окна во двор).

Та же прозрачная формула, что у quietness_proxy (risk = max(w·exp(−d/scale)),
те же веса дорог/ж/д/баров), но считается для точек на каждой стене, а не для
точки отеля. Если отрезок «стена → ближайшая точка источника» проходит сквозь
своё здание, звук экранирован сильно; сквозь соседний дом — частично.
Это не акустический расчёт (нет отражений и дифракции, см. NoiseModelling):
только сравнение сторон одного здания между собой и с порогами quietness_proxy.
"""
from collections import defaultdict
import math
from shapely import STRtree
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points
from app.environment.noise import facade_receivers
from app.geo.geometry import element_shape
from app.geo.osm_provider import osm_id
from app.geo.quietness import ROAD_WEIGHTS
from app.geo.viewshed import compass

SOURCE_RADIUS_M = 400.
OWN_BUILDING_FACTOR = 0.3   # своё здание между окном и дорогой
OTHER_BUILDING_FACTOR = 0.6  # соседний дом между окном и дорогой
LIMITS = ['uncalibrated_heuristic', 'not_db_level', 'no_reflections_or_diffraction', 'aircraft_not_included',
          'facade_points_not_actual_windows']


def sources(elements, around, radius=SOURCE_RADIUS_M):
    result = []
    for item in elements:
        tags = item.get('tags', {})
        if tags.get('railway') == 'rail':
            weight, scale, kind = 1., 180., 'ж/д'
        elif tags.get('amenity') in ('bar', 'pub', 'nightclub'):
            weight, scale, kind = .6, 100., 'бар/клуб'
        elif tags.get('highway') in ROAD_WEIGHTS:
            weight, scale, kind = ROAD_WEIGHTS[tags['highway']], 120., 'дорога'
        else:
            continue
        shape = element_shape(item)
        if shape is not None and shape.distance(around) <= radius:
            result.append({'osm_id': osm_id(item), 'kind': kind, 'name': tags.get('name'), 'weight': weight,
                           'scale': scale, 'shape': shape})
    return result


def side_risks(polygon, elements, neighbours, spacing=12.):
    """{сторона света: {'risk', 'source', 'distance_m', 'shielded'}} — худшая точка на каждой стороне."""
    receivers = facade_receivers(polygon, heights=(1.,), spacing=spacing, offset=1.)
    noise = sources(elements, polygon)
    tree = STRtree(neighbours) if neighbours else None
    sides = defaultdict(lambda: {'risk': 0., 'source': None, 'distance_m': None, 'shielded': None})
    for receiver in receivers:
        point = Point(receiver['x'], receiver['y'])
        side = compass(receiver['azimuth'])
        worst = sides[side]
        for src in noise:
            target = nearest_points(point, src['shape'])[1]
            distance = point.distance(target)
            path = LineString([point, target]) if distance > 0 else None
            factor, shielded = 1., None
            if path is not None and path.crosses(polygon):
                factor, shielded = OWN_BUILDING_FACTOR, 'своё здание'
            elif path is not None and tree is not None and any(
                    path.crosses(neighbours[i]) for i in tree.query(path)):
                factor, shielded = OTHER_BUILDING_FACTOR, 'соседний дом'
            risk = src['weight'] * math.exp(-distance / src['scale']) * factor
            if risk > worst['risk']:
                sides[side] = worst = {'risk': round(risk, 4), 'source': src['name'] or src['kind'],
                                       'kind': src['kind'], 'distance_m': round(distance), 'shielded': shielded}
    return dict(sides)


def category(risk):
    """Те же пороги, что у quietness_proxy: high (тихо) < .25, medium < .6, иначе low."""
    return 'high' if risk < .25 else 'medium' if risk < .6 else 'low'


def summarize(sides):
    if not sides:
        return None
    quiet_side, quiet = min(sides.items(), key=lambda kv: kv[1]['risk'])
    loud_side, loud = max(sides.items(), key=lambda kv: kv[1]['risk'])
    return {'quiet_side': quiet_side, 'quiet_risk': quiet['risk'], 'quiet_category': category(quiet['risk']),
            'loud_side': loud_side, 'loud_risk': loud['risk'], 'loud_category': category(loud['risk']),
            'sides': sides, 'formula': 'max(weight * exp(-distance_m / decay_scale_m)) × экранирование',
            'shielding': {'own_building': OWN_BUILDING_FACTOR, 'neighbour': OTHER_BUILDING_FACTOR}, 'limits': LIMITS}


def explain(summary):
    labels = {'high': 'тихо', 'medium': 'умеренно', 'low': 'шумно'}
    quiet, loud = summary['sides'][summary['quiet_side']], summary['sides'][summary['loud_side']]
    if summary['quiet_side'] == summary['loud_side'] or summary['quiet_category'] == summary['loud_category']:
        return (f'Стороны здания по шуму почти не отличаются: {labels[summary["quiet_category"]]} '
                f'(ближайший источник — {quiet["source"]}, {quiet["distance_m"]} м).')
    text = (f'Тихая сторона — {summary["quiet_side"]} ({labels[summary["quiet_category"]]}'
            + (f', экранирует {quiet["shielded"]}' if quiet['shielded'] else '') + '); '
            f'шумная — {summary["loud_side"]} ({labels[summary["loud_category"]]}: {loud["source"]}, {loud["distance_m"]} м).')
    return text + ' Спросите номер с окнами на тихую сторону.'
