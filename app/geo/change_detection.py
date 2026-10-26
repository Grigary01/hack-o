"""Актуализация вида: что изменилось в зданиях OSM и каких отелей это касается.

Новый дом, надстройка или снос могут открыть или закрыть вид. Сравниваем два
снимка зданий по OSM ID: добавленные, снесённые, изменённые (контур или высота).
Отель затронут, если изменение лежит в радиусе обзора, где здание ещё может
закрыть горизонт, или касается дома, который уже закрывает вид из его окон.
Пересчёт делается только для затронутых отелей.
"""
from app.environment.noise import building_polygon
from app.geo.geometry import metric_point
from app.geo.osm_provider import osm_id
from app.geo.viewshed import building_height

RELEVANCE_RADIUS_M = 1500.  # дальше дом высотой ≤ 30 этажей почти не меняет горизонт с низких этажей


def _buildings(elements):
    result = {}
    for item in elements:
        tags = item.get('tags', {})
        if tags.get('building') and tags['building'] != 'no':
            polygon = building_polygon(item)
            if polygon is not None:
                result[osm_id(item)] = {'polygon': polygon, 'height': building_height(tags)[0], 'tags': tags}
    return result


def diff_buildings(old_elements, new_elements):
    old, new = _buildings(old_elements), _buildings(new_elements)
    changes = []
    for key in new.keys() - old.keys():
        changes.append({'osm_id': key, 'change': 'added', 'polygon': new[key]['polygon'],
                        'height_m': new[key]['height'], 'simulated': new[key]['tags'].get('note') == 'SIMULATED'})
    for key in old.keys() - new.keys():
        changes.append({'osm_id': key, 'change': 'removed', 'polygon': old[key]['polygon'], 'height_m': old[key]['height']})
    for key in old.keys() & new.keys():
        a, b = old[key], new[key]
        if a['height'] != b['height'] or a['polygon'].symmetric_difference(b['polygon']).area > 4:
            changes.append({'osm_id': key, 'change': 'modified', 'polygon': b['polygon'],
                            'height_m': b['height'], 'previous_height_m': a['height']})
    return sorted(changes, key=lambda c: c['osm_id'])


def affected_hotels(changes, hotels, viewshed_details):
    """{hotel_id: [изменения с расстоянием]} для отелей, которых изменения касаются."""
    result = {}
    for hotel in hotels:
        point = metric_point(hotel.lat, hotel.lon)
        details = viewshed_details.get(hotel.id, {})
        blocking = {b for key in ('best_sea', 'best_sunset', 'best_mountain')
                    for b in details.get('base', {}).get(key, {}).get('blocking_buildings', [])}
        hits = []
        for change in changes:
            distance = point.distance(change['polygon'])
            if distance <= RELEVANCE_RADIUS_M or change['osm_id'] in blocking:
                hits.append({k: v for k, v in change.items() if k != 'polygon'} |
                            {'distance_m': round(distance), 'was_blocking': change['osm_id'] in blocking})
        if hits:
            result[hotel.id] = sorted(hits, key=lambda h: h['distance_m'])
    return result


def simulated_building(lat, lon, levels, size_m=30., osm_id_value=-1):
    """Синтетический дом для демонстрации (note=SIMULATED): квадрат size_m × size_m."""
    from app.geo.geometry import PROJECT, UNPROJECT
    x, y = PROJECT(lon, lat)
    h = size_m / 2
    ring = [UNPROJECT(x + dx, y + dy) for dx, dy in ((-h, -h), (h, -h), (h, h), (-h, h), (-h, -h))]
    return {'type': 'way', 'id': osm_id_value, 'tags': {'building': 'apartments', 'building:levels': str(levels),
                                                         'note': 'SIMULATED'},
            'geometry': [{'lon': lo, 'lat': la} for lo, la in ring]}
