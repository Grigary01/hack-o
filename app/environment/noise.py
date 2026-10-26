"""Подготовка реальной геометрии Адлера и адаптер NoiseModelling 5.0.1.

Python отвечает за OSM, метры, привязку фасадов и происхождение входов.
Распространение звука считает внешний NoiseModelling, а НЕ наша эвристика.
По умолчанию без трафика/высот выдаём только подготовку и список пробелов.
Явный scenario=True разрешает учебные допущения; его дБ нельзя использовать
для ранжирования настоящих гостиниц. Java запускается только CLI-командой.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import uuid
from shapely.geometry import Polygon, LineString, Point
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union
from app.core.config import ROOT
from app.geo.geometry import PROJECT, UNPROJECT, metric_point, element_shape
from app.geo.osm_provider import osm_id

VERSION = '5.0.1'
VEHICLES = ('LV', 'MV', 'HGV', 'WAV', 'WBV')
PERIODS = ('D', 'E', 'N')
ROAD_TYPES = {'motorway', 'motorway_link', 'trunk', 'trunk_link', 'primary',
              'primary_link', 'secondary', 'secondary_link', 'tertiary',
              'tertiary_link', 'residential', 'unclassified', 'service', 'living_street'}


def building_polygon(item):
    """Замкнутые ways и multipolygon relations, включая дворы (inner rings)."""
    if item['type'] == 'way':
        coords = item.get('geometry', [])
        if len(coords) < 4 or coords[0] != coords[-1]:
            return None
        result = element_shape(item, polygon=True)
    elif item['type'] == 'relation':
        rings = {'outer': [], 'inner': []}
        for member in item.get('members', []):
            geom = element_shape(member)
            role = member.get('role') or 'outer'
            if isinstance(geom, LineString) and role in rings:
                rings[role].append(geom)
        outer = unary_union(list(polygonize(rings['outer'])))
        inner = unary_union(list(polygonize(rings['inner'])))
        result = outer.difference(inner)
    else:
        return None
    if result is None or result.is_empty or result.geom_type not in ('Polygon', 'MultiPolygon'):
        return None
    return result if result.is_valid else None


def height_m(tags):
    """height в метрах — OSM-значение; этажи ×3 — уже наше предположение."""
    try:
        value = float(tags.get('height', '').removesuffix(' m'))
        if 0 < value <= 500:
            return value, 'osm_height'
    except (ValueError, TypeError):
        pass
    return None, 'missing_height'


def facade_receivers(polygon, heights=(4.,), spacing=10., offset=2.):
    """Обходим внешние стены против часовой стрелки, нормаль вправо — наружу.

Точки равномерны внутри каждого сегмента стены, а не на углах. Фасад обозначен
индексом сегмента и азимутом нормали. Это расчётные точки, не реальные окна.
Дворовые фасады пока исключены; точки внутри соседних зданий удаляются ниже.
"""
    if (not heights or any(not math.isfinite(v) or v <= 0 for v in (*heights, spacing, offset))):
        raise ValueError('Высоты, шаг и отступ должны быть положительными')
    parts = list(polygon.geoms) if polygon.geom_type == 'MultiPolygon' else [polygon]
    points = []
    for part_id, part in enumerate(parts):
        coords = list(orient(part, sign=1).exterior.coords)
        for wall, (a, b) in enumerate(zip(coords, coords[1:])):
            dx, dy = b[0]-a[0], b[1]-a[1]
            length = math.hypot(dx, dy)
            if length < .2:
                continue
            nx, ny = dy/length, -dx/length
            azimuth = math.degrees(math.atan2(nx, ny)) % 360
            count = max(1, math.ceil(length/spacing))
            for i in range(count):
                t = (i+.5)/count
                x, y = a[0]+t*dx+offset*nx, a[1]+t*dy+offset*ny
                if polygon.covers(Point(x, y)):
                    continue
                lon, lat = UNPROJECT(x, y)
                for height in heights:
                    points.append(dict(pk=len(points)+1, x=x, y=y, z=height, lat=lat, lon=lon,
                                       facade=f'{part_id}:{wall}', azimuth=round(azimuth, 1)))
    return points


def prepare_scene(hotel, snapshot, heights=(4.,), scenario=False, traffic=None):
    """traffic: {osm_id: {source_ref, LV_D, LV_SPD_D, ...}} для всех 5 классов.

Не угадываем интенсивность по классу дороги. Учебный сценарий явно одинаков
для всех дорог: LV=100/50/10 авто/час D/E/N, 30 км/ч; другие классы=0.
Это проверка работающего движка, не оценка реального шума Адлера.
"""
    point = metric_point(hotel.lat, hotel.lon)
    buildings, sources, ignored = [], [], []
    relation_members = {m['ref'] for item in snapshot['elements']
                        if item['type'] == 'relation' and item.get('tags', {}).get('building')
                        and building_polygon(item) is not None
                        for m in item.get('members', []) if m.get('type') == 'way'}
    for item in snapshot['elements']:
        tags = item.get('tags', {})
        oid = osm_id(item)
        if tags.get('building') and tags['building'] != 'no':
            if item['type'] == 'way' and item['id'] in relation_members:
                continue
            geom = building_polygon(item)
            if geom is None:
                ignored.append(oid)
                continue
            if geom.distance(point) > 650:
                continue
            height, method = height_m(tags)
            if height is None and scenario:
                height, method = 9., 'scenario_assumed_9m'
            buildings.append(dict(pk=len(buildings)+1, osm_id=oid, geom=geom,
                                  height=height, height_method=method))
        kind = ('road' if tags.get('highway') in ROAD_TYPES else
                'rail' if tags.get('railway') == 'rail' else
                'nightlife' if tags.get('amenity') in ('bar', 'pub', 'nightclub') else None)
        geom = element_shape(item)
        if kind and geom is not None and geom.distance(point) <= 600:
            sources.append(dict(osm_id=oid, kind=kind, geom=geom, tags=tags))
    # Только содержащий точку контур; ближайший соседний дом не назначается отелю.
    own = [b for b in buildings if b['osm_id'] == hotel.id or b['geom'].covers(point)]
    report = dict(kind='noise', hotel_id=hotel.id, collected_at=datetime.now(timezone.utc).isoformat(),
                  status='prepared', engine=f'NoiseModelling {VERSION}', scenario=scenario,
                  snapshot_metadata=snapshot['metadata'], crs='EPSG:32637',
                  periods={'D':'06–18', 'E':'18–22', 'N':'22–06'},
                  source_url='https://noise-planet.org/noisemodelling.html',
                  limits=['road_noise_only', 'aircraft_not_modeled', 'rail_not_modeled',
                          'nightlife_not_modeled', 'flat_terrain', 'default_ground_and_weather',
                          'osm_may_be_incomplete', 'facade_points_not_actual_windows',
                          'courtyard_facades_not_sampled', 'outdoor_not_indoor'],
                  gaps=[], receivers=[], levels=[], buildings_count=len(buildings),
                  source_counts={k: sum(s['kind'] == k for s in sources) for k in ('road','rail','nightlife')},
                  invalid_buildings=ignored, missing_height_count=sum(b['height'] is None for b in buildings))
    if len(own) != 1:
        report.update(status='needs_data', gaps=['missing_or_ambiguous_hotel_building'])
        return report, None
    report['building_osm_id'] = own[0]['osm_id']
    report['building_match'] = 'osm_id' if own[0]['osm_id'] == hotel.id else 'contains_hotel_point_unverified'
    if own[0]['height'] is not None and any(z >= own[0]['height'] for z in heights):
        report.update(status='needs_data', gaps=['receiver_at_or_above_roof'])
        return report, None
    receivers = facade_receivers(own[0]['geom'], heights)
    receivers = [r for r in receivers if not any(b['geom'].covers(Point(r['x'], r['y'])) for b in buildings)]
    if not receivers:
        report['gaps'].append('no_receivers')
    # Прямая видимость — только диагностика. Отражение/дифракцию считает Java.
    for receiver in receivers:
        p = Point(receiver['x'], receiver['y'])
        nearby = []
        for source in sources:
            if p.distance(source['geom']) > 500:
                continue
            from shapely.ops import nearest_points
            q = nearest_points(p, source['geom'])[1]
            ray = LineString([p, q])
            obstacles = [b['osm_id'] for b in buildings if ray.crosses(b['geom'])]
            nearby.append(dict(osm_id=source['osm_id'], kind=source['kind'],
                               distance_m=round(p.distance(q), 1), planar_obstacles=obstacles))
        receiver['nearby_sources'] = sorted(nearby, key=lambda s: s['distance_m'])[:10]
    report['receivers'] = receivers
    roads = []
    for source in sources:
        if source['kind'] != 'road' or source['geom'].geom_type != 'LineString':
            continue
        data = (traffic or {}).get(source['osm_id'])
        if scenario:
            data = {'source_ref': 'SYNTHETIC scenario, not Adler traffic counts'}
            for period, count in zip(PERIODS, (100., 50., 10.)):
                for vehicle in VEHICLES:
                    data[f'{vehicle}_{period}'] = count if vehicle == 'LV' else 0.
                    data[f'{vehicle}_SPD_{period}'] = 30.
        if data is None:
            report['gaps'].append('missing_traffic:' + source['osm_id'])
            continue
        validate_traffic(data)
        # Высота источника дорожного шума 0.05 м, ровная поверхность земли.
        geom3d = LineString([(x, y, .05) for x, y in source['geom'].coords])
        roads.append(dict(pk=len(roads)+1, osm_id=source['osm_id'], wkt=geom3d.wkt, traffic=data))
    if report['missing_height_count']:
        report['gaps'].append('missing_building_heights')
    if not roads:
        report['gaps'].append('no_roads_with_traffic')
    report['status'] = 'needs_data' if report['gaps'] else 'ready_scenario' if scenario else 'ready'
    report['assumed_height_count'] = sum(b['height_method'].startswith('scenario') for b in buildings)
    report['traffic_source_refs'] = sorted({r['traffic']['source_ref'] for r in roads})
    scene = None if report['gaps'] else dict(
        buildings=[{k:v for k,v in b.items() if k != 'geom'} | {'wkt': b['geom'].wkt} for b in buildings],
        roads=roads, receivers=receivers)
    return report, scene


def validate_traffic(data):
    if not isinstance(data.get('source_ref'), str) or not data['source_ref'].strip():
        raise ValueError('Трафику нужен source_ref')
    for p in PERIODS:
        for v in VEHICLES:
            for key, upper in ((f'{v}_{p}', 100000), (f'{v}_SPD_{p}', 200)):
                value = data.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= upper:
                    raise ValueError('Неверное/пропущенное поле трафика: ' + key)
            if data[f'{v}_{p}'] > 0 and data[f'{v}_SPD_{p}'] == 0:
                raise ValueError('Ненулевому потоку нужна скорость')


def run_noisemodelling(report, scene, nm_home, java_home=None, output_root=None):
    """Отдельный процесс, собственная H2 DB для каждого запуска, timeout 5 минут.

Не используем shell=True: пути и данные пользователя не становятся shell-кодом.
Отчёт сохраняет вход, версию, контрольную сумму и путь к логу для воспроизведения.
"""
    if scene is None:
        raise ValueError('Сначала заполните недостающие входные данные')
    nm_home = Path(nm_home).resolve()
    if not (nm_home/'lib'/f'noisemodelling-jdbc-{VERSION}.jar').is_file():
        raise ValueError(f'Нужен официальный NoiseModelling without_gui {VERSION}')
    work = (Path(output_root or ROOT/'runtime/noise_runs') / uuid.uuid4().hex).resolve()
    work.mkdir(parents=True)
    source = work/'input.json'
    source.write_text(json.dumps(scene, ensure_ascii=False, allow_nan=False))
    env = dict(os.environ)
    if java_home:
        env['JAVA_HOME'] = str(Path(java_home).resolve())
    env['JAVA_OPTS'] = '-Xmx1g'
    command = ['sh', str(nm_home/'bin/wps_scripts'), '-w', str(work), '-s',
               str(ROOT/'scripts/noise_pipeline.groovy'), '-inputPath', str(source),
               '-nmHome', str(nm_home), '-outputPath', str(work/'levels.json')]
    with (work/'engine.log').open('w') as log:
        result = subprocess.run(command, cwd=nm_home, env=env, stdout=log,
                                stderr=subprocess.STDOUT, timeout=300)
    if result.returncode != 0 or not (work/'levels.json').exists():
        raise RuntimeError(f'NoiseModelling завершился с ошибкой; лог {work / "engine.log"}')
    levels = json.loads((work/'levels.json').read_text())
    expected = {(r['pk'], p) for r in scene['receivers'] for p in PERIODS}
    actual = {(r['receiver_id'], r['period']) for r in levels}
    if not expected.issubset(actual) or any(not isinstance(r['laeq_db'], (int,float)) or
                                          not math.isfinite(r['laeq_db']) for r in levels):
        raise ValueError('Неполный/нечисловой результат NoiseModelling')
    report.update(status='scenario' if report['scenario'] else 'modeled', levels=levels,
                  input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  run_directory=str(work.relative_to(ROOT)) if work.is_relative_to(ROOT) else str(work),
                  engine_version=VERSION)
    (work/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return report
