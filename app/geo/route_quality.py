"""Реальная доступность пешего пути до пляжа: подъёмы и переходы через трассы.

Длина пути уже считается по графу OSM (routing.py). Здесь тот же маршрут
проверяется на то, о чём гость узнаёт только на месте:
- набор высоты туда и обратно по рельефу Copernicus (после открытия, без домов);
- переходы в одном уровне через trunk/primary/secondary и их тип по OSM
  (светофор, зебра, нерегулируемый, не обозначен); мосты и тоннели — не переход;
- лестницы на маршруте (важно с коляской).

Рельеф GLO-30 имеет погрешность по высоте порядка 2–4 м и шаг 30 м: набор высоты
меньше ~3 м неотличим от шума, поэтому используется гистерезис 1 м.
"""
import math
import numpy as np
from shapely.geometry import LineString, Point
from app.geo.geometry import element_shape, metric_point
from app.geo.osm_provider import osm_id

BUSY_ROADS = {'trunk': 'магистраль', 'trunk_link': 'магистраль', 'primary': 'главная улица',
              'primary_link': 'главная улица', 'secondary': 'улица районного значения',
              'secondary_link': 'улица районного значения'}
CROSSING_KIND = {'traffic_signals': 'светофор', 'marked': 'зебра', 'zebra': 'зебра',
                 'uncontrolled': 'нерегулируемый', 'unmarked': 'без разметки'}
SAMPLE_STEP_M = 10.
HYSTERESIS_M = 1.
CROSSING_SNAP_M = 12.
SAME_ROAD_MERGE_M = 40.  # две проезжие части одной улицы — один переход
LIMITS = ['dem_vertical_error_2_4m', 'crossing_type_from_osm_tags', 'route_entry_points_approximate',
          'underpasses_only_if_tagged']


def climb(elevations):
    """Набор и сброс высоты с гистерезисом: шум рельефа меньше 1 м не копится."""
    ascent = descent = 0.
    anchor = elevations[0]
    for value in elevations[1:]:
        if value - anchor >= HYSTERESIS_M:
            ascent += value - anchor
            anchor = value
        elif anchor - value >= HYSTERESIS_M:
            descent += anchor - value
            anchor = value
    return ascent, descent


def max_grade(elevations, step=SAMPLE_STEP_M, window=3):
    """Самый крутой участок ~30 м, в процентах."""
    if len(elevations) <= window:
        return 0.
    diffs = np.abs(np.array(elevations[window:]) - np.array(elevations[:-window]))
    return float(diffs.max() / (step * window) * 100)


def crossing_points(elements):
    points = []
    for item in elements:
        tags = item.get('tags', {})
        if tags.get('highway') in ('crossing', 'traffic_signals') or tags.get('footway') == 'crossing':
            shape = element_shape(item)
            if shape is not None:
                kind = 'traffic_signals' if tags.get('highway') == 'traffic_signals' else tags.get('crossing')
                points.append((shape, CROSSING_KIND.get(kind, 'переход без уточнения типа')))
    return points


def analyze(route, graph, elements, ground_at):
    """route — RouteResult с node_ids; ground_at(x, y) — высота земли, м."""
    if route.distance_m is None:
        return None
    if len(route.node_ids) < 2:  # отель у самого пляжа: путь только из отрезков привязки
        return {'ascent_to_beach_m': 0., 'ascent_back_m': 0., 'climb_m': 0., 'max_grade_pct': 0.,
                'busy_crossings': 0, 'crossings': [], 'stairs_segments': 0, 'sample_step_m': SAMPLE_STEP_M,
                'hysteresis_m': HYSTERESIS_M, 'route_length_m': round(route.distance_m), 'limits': LIMITS}
    nodes = [metric_point(graph.nodes[n]['y'], graph.nodes[n]['x']) for n in route.node_ids]
    line = LineString([(p.x, p.y) for p in nodes])
    distances = np.arange(0, line.length + SAMPLE_STEP_M, SAMPLE_STEP_M).clip(max=line.length)
    elevations = [ground_at(*line.interpolate(d).coords[0]) for d in distances]
    up, down = climb(elevations)

    roads = []
    for item in elements:
        tags = item.get('tags', {})
        if tags.get('highway') in BUSY_ROADS and not tags.get('bridge') and not tags.get('tunnel'):
            shape = element_shape(item)
            if shape is not None:
                roads.append((osm_id(item), item['id'], tags, shape))
    marks = crossing_points(elements)
    crossings, stairs = [], 0
    for (u, v), a, b in zip(zip(route.node_ids, route.node_ids[1:]), nodes, nodes[1:]):
        edge = min(graph[u][v].values(), key=lambda e: e['length'])
        if edge.get('highway') == 'steps':
            stairs += 1
        if str(edge.get('bridge', '')).lower() not in ('', 'no', 'nan') or \
           str(edge.get('tunnel', '')).lower() not in ('', 'no', 'nan'):
            continue  # пешеходный мост/подземный переход — не пересечение в одном уровне
        segment = LineString([a, b])
        edge_ways = str(edge.get('osmid', ''))
        for road_id, raw_id, tags, shape in roads:
            if str(raw_id) in edge_ways:
                continue  # идём вдоль этой дороги (тротуар), а не пересекаем её
            hit = segment.intersection(shape)
            if hit.is_empty or hit.geom_type not in ('Point', 'MultiPoint'):
                continue
            point = hit if hit.geom_type == 'Point' else list(hit.geoms)[0]
            near = [kind for mark, kind in marks if mark.distance(point) <= CROSSING_SNAP_M]
            name = tags.get('name') or tags.get('ref') or BUSY_ROADS[tags['highway']]
            duplicate = any(c['name'] == name and Point(c['x'], c['y']).distance(point) <= SAME_ROAD_MERGE_M
                            for c in crossings)
            if not duplicate:
                crossings.append({'road_osm_id': road_id, 'name': name, 'highway': tags['highway'],
                                  'class': BUSY_ROADS[tags['highway']],
                                  'crossing': near[0] if near else 'не обозначен в OSM',
                                  'x': round(point.x, 1), 'y': round(point.y, 1)})
    return {
        'ascent_to_beach_m': round(up, 1), 'ascent_back_m': round(down, 1),
        'climb_m': round(max(up, down), 1), 'max_grade_pct': round(max_grade(elevations), 1),
        'busy_crossings': len(crossings), 'crossings': crossings, 'stairs_segments': stairs,
        'sample_step_m': SAMPLE_STEP_M, 'hysteresis_m': HYSTERESIS_M, 'route_length_m': round(line.length),
        'limits': LIMITS,
    }


def explain_climb(result):
    text = f'Подъёмы на пути к пляжу: туда ≈ {result["ascent_to_beach_m"]:g} м, обратно ≈ {result["ascent_back_m"]:g} м.'
    if result['climb_m'] < 3:
        text += ' Практически ровно (в пределах точности рельефа).'
    else:  # на ровном участке уклон — шум рельефа, показываем только при заметном подъёме
        text += f' Самый крутой участок ≈ {result["max_grade_pct"]:g}%.'
    if result['stairs_segments']:
        text += ' На маршруте есть лестница.'
    return text


def explain_crossings(result):
    if not result['crossings']:
        return 'Оживлённые дороги на пути к пляжу переходить не нужно (по OSM).'
    parts = [f'{c["name"]} ({c["crossing"]})' for c in result['crossings']]
    word = 'переход' if len(parts) == 1 else 'перехода' if len(parts) < 5 else 'переходов'
    return f'{len(parts)} {word} через оживлённые дороги: ' + ', '.join(parts) + '.'
