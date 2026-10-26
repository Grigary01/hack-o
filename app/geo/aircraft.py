"""Воздействие авиашума аэропорта Сочи (AER) по геометрии ВПП из OSM.

Модель намеренно простая и прозрачная. От каждого торца ВПП наружу идёт
прямая траектория по продолжению оси с глиссадой 3° (порог пересекается на 15 м).
Этот профиль используем и для заходов, и для взлётов: взлётный набор круче,
поэтому оценка консервативная (самолёт «ниже», чем на самом деле при взлёте).
Для отеля считаем кратчайшее наклонное расстояние до траектории или до самой ВПП.

Децибелы не выдаём: нет реальных треков (ADS-B), расписания, распределения
по полосам и типам самолётов. Категории — по наклонному расстоянию:
для A320 на заходе Lmax порядка 85–90 дБА на 300 м и −6 дБ на удвоение расстояния;
это ориентир для порогов, а не результат расчёта.
"""
import math
import numpy as np
from shapely.geometry import LineString
from app.geo.geometry import element_shape, metric_point
from app.geo.osm_provider import osm_id

GLIDE_SLOPE_DEG = 3.0
THRESHOLD_CROSSING_M = 15.0
TRACK_LENGTH_M = 12000.0
OBSERVER_ABOVE_GROUND_M = 10.0  # ~3-й этаж
HIGH_EXPOSURE_M = 800.0
MEDIUM_EXPOSURE_M = 2000.0
LIMITS = ['straight_tracks_assumed', 'runway_usage_unknown', 'approach_profile_used_for_departures',
          'no_traffic_counts', 'night_operations_unknown', 'not_db_level', 'helicopters_not_modeled']


def runways(elements):
    """Оси ВПП в UTM: только aeroway=runway с геометрией линии."""
    result = []
    for item in elements:
        tags = item.get('tags', {})
        if tags.get('aeroway') != 'runway':
            continue
        line = element_shape(item)
        if isinstance(line, LineString) and line.length > 500:
            result.append({'osm_id': osm_id(item), 'ref': tags.get('ref'), 'line': line})
    return result


def runway_ends(runway):
    """Два торца: точка порога и единичный вектор наружу от ВПП."""
    coords = list(runway['line'].coords)
    ends = []
    for (x, y), (ox, oy) in ((coords[0], coords[-1]), (coords[-1], coords[0])):
        length = math.hypot(x - ox, y - oy)
        ux, uy = (x - ox) / length, (y - oy) / length
        # Курс захода на этот торец противоположен вектору наружу.
        bearing = (math.degrees(math.atan2(-ux, -uy))) % 360
        ends.append({'x': x, 'y': y, 'ux': ux, 'uy': uy, 'landing_heading': round(bearing)})
    return ends


def exposure(lat, lon, runway_list, ground_at):
    """ground_at(x, y) → высота земли, м. Возвращает категорию и разбор."""
    point = metric_point(lat, lon)
    observer_z = ground_at(point.x, point.y) + OBSERVER_ABOVE_GROUND_M
    candidates = []
    s = np.arange(0., TRACK_LENGTH_M + 1, 25.)
    for runway in runway_list:
        runway_ground = float(np.mean([ground_at(x, y) for x, y in runway['line'].coords]))
        horizontal = point.distance(runway['line'])
        candidates.append({'kind': 'runway', 'runway': runway['ref'], 'osm_id': runway['osm_id'],
                           'slant_m': math.hypot(horizontal, runway_ground - observer_z),
                           'horizontal_m': horizontal, 'aircraft_height_m': 0.})
        for end in runway_ends(runway):
            dx, dy = point.x - end['x'], point.y - end['y']
            along = dx * end['ux'] + dy * end['uy']
            lateral = abs(dx * end['uy'] - dy * end['ux'])
            track_z = (ground_at(end['x'], end['y']) + THRESHOLD_CROSSING_M
                       + s * math.tan(math.radians(GLIDE_SLOPE_DEG)))
            slant = np.sqrt((along - s) ** 2 + lateral ** 2 + (track_z - observer_z) ** 2)
            i = int(slant.argmin())
            candidates.append({'kind': 'extended_centerline', 'runway': runway['ref'], 'osm_id': runway['osm_id'],
                               'landing_heading': end['landing_heading'], 'slant_m': float(slant[i]),
                               'along_track_m': float(s[i]), 'lateral_m': lateral,
                               'aircraft_height_m': float(track_z[i] - ground_at(end['x'], end['y']))})
    if not candidates:
        return None, {'reason': 'no_runways_in_snapshot'}
    nearest = min(candidates, key=lambda c: c['slant_m'])
    category = ('high' if nearest['slant_m'] < HIGH_EXPOSURE_M else
                'medium' if nearest['slant_m'] < MEDIUM_EXPOSURE_M else 'low')
    rounded = lambda c: {k: round(v) if isinstance(v, float) else v for k, v in c.items()}
    return category, {
        'nearest': rounded(nearest),
        'by_track': sorted((rounded(c) for c in candidates), key=lambda c: c['slant_m']),
        'thresholds_m': {'high': HIGH_EXPOSURE_M, 'medium': MEDIUM_EXPOSURE_M},
        'method': {'glide_slope_deg': GLIDE_SLOPE_DEG, 'threshold_crossing_m': THRESHOLD_CROSSING_M,
                   'track_length_m': TRACK_LENGTH_M, 'observer_above_ground_m': OBSERVER_ABOVE_GROUND_M},
        'limits': LIMITS,
    }


def explanation(nearest):
    """Текст для гостя по ближайшей траектории."""
    if nearest['kind'] == 'runway':
        return f'До ВПП {nearest["runway"]} аэропорта Сочи ≈ {nearest["horizontal_m"]} м.'
    return (f'Траектория захода/взлёта по оси ВПП {nearest["runway"]} (посадочный курс {nearest["landing_heading"]}°) '
            f'проходит ≈ в {nearest["slant_m"]} м от окна 3-го этажа; самолёт там на высоте ≈ {nearest["aircraft_height_m"]} м.')
