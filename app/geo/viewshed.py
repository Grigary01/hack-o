"""Вид из окон: море и закат по рельефу, высотам зданий OSM и положению солнца.

Модель поверхности = рельеф Copernicus GLO-30 (после морфологического открытия,
чтобы убрать частично попавшие в DSM дома) + контуры зданий OSM с высотой
(height или building:levels × 3 м). Море — полигон справа от OSM coastline.

Для каждой точки фасада (снаружи стены, по нормали) и каждого этажа строим
лучи в секторе окна ±60° с шагом 1° на расстояние до 20 км. Точка луча видна,
если её угол возвышения выше максимума всех более близких точек (с учётом
кривизны Земли и рефракции). Отсюда:
- доля сектора окна, в которой видно море;
- угол горизонта по азимутам → виден ли низкое солнце в каждом месяце.

Это расчётные точки на стенах, а не реальные окна: где окна и балконы,
мы не знаем. Деревья, навесы и рекламные щиты не моделируются.
Неизвестные высоты соседних домов перебираются в трёх сценариях: если вывод
одинаков во всех — уверенность medium, иначе low. high без проверки на месте не бывает.
"""
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
import shapely
from shapely.geometry import Point, box
from shapely.ops import linemerge, split, unary_union
from app.environment.noise import building_polygon, facade_receivers
from app.geo.geometry import PROJECT, UNPROJECT, metric_point, element_shape
from app.geo.osm_provider import osm_id
from app.geo.solar import monthly_sunset_tracks

EARTH_RADIUS_M = 6371008.8
REFRACTION_K = 0.13  # стандартный коэффициент земной рефракции для геодезии
EFFECTIVE_RADIUS_M = EARTH_RADIUS_M / (1 - REFRACTION_K)
FLOOR_HEIGHT_M = 3.0
EYE_ABOVE_FLOOR_M = 1.6  # глаза стоящего человека; пол 1-го этажа на уровне земли
WINDOW_HALF_FOV = 60  # насколько в сторону можно смотреть из окна, градусы
ASSUMED_HOTEL_LEVELS = 3
# Неизвестная высота соседа: low/base/high. 6.5 м ~ два этажа частного сектора Адлера.
UNKNOWN_HEIGHT_SCENARIOS = {'low': 3.0, 'base': 6.5, 'high': 12.0}
LOW_STRUCTURES = {'garage', 'garages', 'shed', 'carport', 'kiosk', 'hut', 'roof', 'toilets', 'service'}
SEA_PARTIAL_SHARE = 0.03  # ≥ ~4° моря из 121° сектора окна — «просвет»
SEA_WIDE_SHARE = 0.25
SUNSET_LOW_ALTITUDE = 3.0  # солнце видно ниже 3° — «закат виден»
MOUNTAIN_MIN_M = 300.  # видимый рельеф выше 300 м — «горы» (отроги Кавказа, Ахун)
SUNSET_SEA_ALTITUDE = 1.0  # и опускается к морскому горизонту
MONTHS_RU = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль',
             'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
COMPASS_RU = ['С', 'СВ', 'В', 'ЮВ', 'Ю', 'ЮЗ', 'З', 'СЗ']
LIMITS = ['facade_points_not_actual_windows', 'vegetation_not_modeled', 'self_occlusion_not_modeled',
          'balconies_and_awnings_not_modeled', 'dem_acquired_2011_2015', 'osm_building_heights_incomplete',
          'floor_height_assumed_3m']

# Шаг вдоль луча растёт с расстоянием: вблизи важны узкие просветы между домами.
DISTANCES_M = np.concatenate([np.arange(2., 400., 2.), np.arange(400., 2000., 6.),
                              np.arange(2000., 20000., 30.)])


def building_height(tags):
    """(высота над землёй, метод). Этажи × 3 м — уже наше допущение, не факт OSM."""
    try:
        value = float(str(tags.get('height', '')).removesuffix('m').strip())
        if 0 < value <= 500:
            return value, 'osm_height'
    except ValueError:
        pass
    try:
        levels = float(tags.get('building:levels', ''))
        roof = float(tags.get('roof:levels', 0) or 0)
        if 0 < levels <= 100:
            return (levels + roof) * FLOOR_HEIGHT_M, 'osm_levels'
    except ValueError:
        pass
    if tags.get('building') in LOW_STRUCTURES:
        return 3.0, 'type_default_low_structure'
    return None, 'missing'


def compass(azimuth):
    return COMPASS_RU[int(((azimuth % 360) + 22.5) // 45) % 8]


def month_ranges(months):
    """[4,5,6,7,8] → 'апрель–август'; учитывает переход через декабрь."""
    if not months:
        return ''
    if len(months) == 12:
        return 'круглый год'
    months = sorted(months)
    runs, start, prev = [], months[0], months[0]
    for m in months[1:] + [None]:
        if m != prev + 1 if m is not None else True:
            runs.append([start, prev])
            if m is not None:
                start = m
        if m is not None:
            prev = m
    if len(runs) > 1 and runs[0][0] == 1 and runs[-1][1] == 12:
        runs[0][0] = runs.pop()[0]
    return ', '.join(MONTHS_RU[a-1] if a == b else f'{MONTHS_RU[a-1]}–{MONTHS_RU[b-1]}' for a, b in runs)


def opening(grid, size):
    """Морфологическое открытие (min, затем max): убирает узкие «бугры» домов
    и деревьев шириной меньше окна, сохраняя склоны рельефа."""
    pad = size // 2
    eroded = sliding_window_view(np.pad(grid, pad, mode='edge'), (size, size)).min(axis=(2, 3))
    return sliding_window_view(np.pad(eroded, pad, mode='edge'), (size, size)).max(axis=(2, 3))


@dataclass
class Grid:
    """Регулярная сетка в UTM 37N; значения в центрах ячеек, строки — с юга на север."""
    x0: float
    y0: float
    step: float
    shape: tuple

    @classmethod
    def around(cls, bounds, step):
        minx, miny, maxx, maxy = bounds
        return cls(minx, miny, step, (int((maxy-miny)//step)+1, int((maxx-minx)//step)+1))

    def centers(self, rows=slice(None), cols=slice(None)):
        r = np.arange(self.shape[0])[rows]
        c = np.arange(self.shape[1])[cols]
        return np.meshgrid(self.x0 + (c+.5)*self.step, self.y0 + (r+.5)*self.step)

    def index(self, x, y):
        """Индексы ячеек и маска «внутри сетки» для массивов координат."""
        col = np.floor((x - self.x0) / self.step).astype(np.int64)
        row = np.floor((y - self.y0) / self.step).astype(np.int64)
        inside = (row >= 0) & (row < self.shape[0]) & (col >= 0) & (col < self.shape[1])
        return np.where(inside, row, 0), np.where(inside, col, 0), inside

    def bilinear(self, values, x, y):
        fx = (x - self.x0) / self.step - .5
        fy = (y - self.y0) / self.step - .5
        c0, r0 = np.floor(fx).astype(np.int64), np.floor(fy).astype(np.int64)
        inside = (r0 >= 0) & (r0 < self.shape[0]-1) & (c0 >= 0) & (c0 < self.shape[1]-1)
        r0, c0 = np.where(inside, r0, 0), np.where(inside, c0, 0)
        tx, ty = fx - c0, fy - r0
        result = (values[r0, c0]*(1-tx)*(1-ty) + values[r0, c0+1]*tx*(1-ty)
                  + values[r0+1, c0]*(1-tx)*ty + values[r0+1, c0+1]*tx*ty)
        return np.where(inside, result, np.nan)

    def rasterize(self, geometry, out, value):
        """Записывает value в ячейки, центр которых внутри geometry."""
        minx, miny, maxx, maxy = geometry.bounds
        c0, c1 = max(0, int((minx-self.x0)//self.step)), min(self.shape[1], int((maxx-self.x0)//self.step)+1)
        r0, r1 = max(0, int((miny-self.y0)//self.step)), min(self.shape[0], int((maxy-self.y0)//self.step)+1)
        if c0 >= c1 or r0 >= r1:
            return 0
        xs, ys = self.centers(slice(r0, r1), slice(c0, c1))
        mask = shapely.contains_xy(geometry, xs, ys)
        target = out[r0:r1, c0:c1]
        if np.ndim(value) == 0:
            target[mask] = value
        else:
            target[mask] = value[r0:r1, c0:c1][mask]
        return int(mask.sum())


def sea_polygon(coastline_elements, bounds):
    """Море = части прямоугольника справа от coastline (в OSM суша всегда слева)."""
    lines = [element_shape(e) for e in coastline_elements if e.get('tags', {}).get('natural') == 'coastline']
    lines = [l for l in lines if l is not None and l.geom_type == 'LineString']
    if not lines:
        raise ValueError('В выгрузке нет natural=coastline')
    frame = box(*bounds)
    merged = unary_union(lines)
    if merged.geom_type == 'MultiLineString':
        merged = linemerge(merged)
    merged = merged.intersection(frame)
    pieces = list(split(frame, merged).geoms)
    probes = []
    for line in lines:
        coords = list(line.coords)
        for (ax, ay), (bx, by) in zip(coords, coords[1:]):
            length = math.hypot(bx-ax, by-ay)
            if length > 1:
                # Нормаль вправо от направления линии, 3 м от берега.
                probes.append(Point((ax+bx)/2 + 3*(by-ay)/length, (ay+by)/2 - 3*(bx-ax)/length))
    probes = [p for p in probes if frame.contains(p)]
    sea = [piece for piece in pieces
           if sum(piece.contains(p) for p in probes) > len(probes) * 0.05]
    if not sea or len(sea) == len(pieces):
        # Линия, не пересекающая рамку насквозь, не делит её: всё стало бы «морем».
        raise ValueError('Не удалось определить сторону моря по coastline')
    return unary_union(sea)


@dataclass
class HotelBuilding:
    osm_id: str
    polygon: object
    levels: int
    levels_source: str
    match: str


@dataclass
class ViewshedScene:
    """Загруженные и растеризованные входы. Строится один раз на весь пересчёт."""
    dem_grid: Grid
    dtm: np.ndarray
    far_sea: np.ndarray
    near_grid: Grid
    near_sea: np.ndarray
    bgrid: Grid
    bheight: np.ndarray
    bunknown: np.ndarray
    bid: np.ndarray
    buildings: list
    inputs: dict
    by_osm_id: dict = field(default_factory=dict)

    @classmethod
    def load(cls, environment_dir: Path, hotel_bbox, dem_step=30., near_step=10., building_step=2.):
        buildings_raw = json.loads((environment_dir/'osm_buildings.json').read_text())
        coast_raw = json.loads((environment_dir/'osm_coastline.json').read_text())
        dem_meta = json.loads((environment_dir/'dem_copernicus_glo30.json').read_text())
        dem_path = environment_dir/'dem_copernicus_glo30.npz'
        dem = np.load(dem_path)['elevation_dm'].astype(np.float32) / 10
        if hashlib.sha256(dem_path.read_bytes()).hexdigest() != dem_meta['sha256']:
            raise ValueError('Контрольная сумма DEM не совпадает с метаданными')

        # 1. Рельеф: открытие окном ~150 м на исходной сетке, затем перенос в UTM.
        a, _, c, _, e, f = dem_meta['transform']
        rows, cols = dem.shape
        ground = opening(dem, 5)
        b = dem_meta['bounds']
        corners = [PROJECT(lon, lat) for lon, lat in ((b['west'], b['south']), (b['east'], b['south']),
                                                      (b['west'], b['north']), (b['east'], b['north']))]
        # Внутренний прямоугольник: UTM-сетка не должна выходить за границы DEM.
        inner = (max(corners[0][0], corners[2][0]), max(corners[0][1], corners[1][1]),
                 min(corners[1][0], corners[3][0]), min(corners[2][1], corners[3][1]))
        dem_grid = Grid.around(inner, dem_step)
        xs, ys = dem_grid.centers()
        lon, lat = UNPROJECT(xs, ys)
        fc, fr = (lon - c) / a - .5, (lat - f) / e - .5
        c0 = np.clip(np.floor(fc).astype(np.int64), 0, cols-2)
        r0 = np.clip(np.floor(fr).astype(np.int64), 0, rows-2)
        tx, ty = np.clip(fc-c0, 0, 1), np.clip(fr-r0, 0, 1)
        dtm = (ground[r0, c0]*(1-tx)*(1-ty) + ground[r0, c0+1]*tx*(1-ty)
               + ground[r0+1, c0]*(1-tx)*ty + ground[r0+1, c0+1]*tx*ty).astype(np.float32)

        # 2. Море: грубая сетка на всю область и точная 10 м вокруг отелей (±2 км).
        sea = sea_polygon(coast_raw['elements'], inner)
        shapely.prepare(sea)
        far_sea = shapely.contains_xy(sea, xs, ys)
        s, w, n, e_ = hotel_bbox
        (hx0, hy0), (hx1, hy1) = PROJECT(w, s), PROJECT(e_, n)
        near_grid = Grid.around((hx0-2000, hy0-2000, hx1+2000, hy1+2000), near_step)
        nx, ny = near_grid.centers()
        near_sea = shapely.contains_xy(sea, nx, ny)

        # 3. Здания: известная высота, маска «высота неизвестна», номер здания.
        relation_members = {m['ref'] for item in buildings_raw['elements']
                            if item['type'] == 'relation' and item.get('tags', {}).get('building')
                            for m in item.get('members', []) if m.get('type') == 'way'}
        buildings = []
        for item in buildings_raw['elements']:
            tags = item.get('tags', {})
            if not tags.get('building') or tags['building'] == 'no':
                continue
            if item['type'] == 'way' and item['id'] in relation_members:
                continue
            polygon = building_polygon(item)
            if polygon is None:
                continue
            height, method = building_height(tags)
            buildings.append({'osm_id': osm_id(item), 'polygon': polygon, 'height': height,
                              'method': method, 'tags': tags})
        extent = unary_union([x['polygon'].envelope for x in buildings]).bounds
        bgrid = Grid.around(extent, building_step)
        bheight = np.zeros(bgrid.shape, np.float32)
        bunknown = np.zeros(bgrid.shape, bool)
        bid = np.full(bgrid.shape, -1, np.int32)
        # Сначала низкие: при наложении контуров побеждает более высокое здание.
        for index in sorted(range(len(buildings)), key=lambda i: buildings[i]['height'] or 0):
            item = buildings[index]
            bid_written = bgrid.rasterize(item['polygon'], bid, index)
            if item['height'] is None:
                bgrid.rasterize(item['polygon'], bunknown, True)
            else:
                bgrid.rasterize(item['polygon'], bheight, item['height'])
            item['cells'] = bid_written
        inputs = {
            'buildings': {'path': 'data/environment/osm_buildings.json',
                          'osm_base': buildings_raw['metadata'].get('osm_base'),
                          'query_sha256': buildings_raw['metadata']['query_sha256'],
                          'count': len(buildings),
                          'with_height': sum(x['height'] is not None for x in buildings)},
            'coastline': {'path': 'data/environment/osm_coastline.json',
                          'osm_base': coast_raw['metadata'].get('osm_base'),
                          'query_sha256': coast_raw['metadata']['query_sha256']},
            'dem': {'path': 'data/environment/dem_copernicus_glo30.npz', 'sha256': dem_meta['sha256'],
                    'product': dem_meta['product'], 'attribution': dem_meta['attribution']},
        }
        scene = cls(dem_grid, dtm, far_sea, near_grid, near_sea, bgrid, bheight, bunknown, bid,
                    buildings, inputs)
        scene.by_osm_id = {x['osm_id']: i for i, x in enumerate(buildings)}
        return scene

    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.inputs, sort_keys=True).encode()).hexdigest()

    def building_at(self, x, y):
        row, col, inside = self.bgrid.index(np.array([x]), np.array([y]))
        return int(self.bid[row[0], col[0]]) if inside[0] else -1

    def hotel_building(self, hotel, max_snap_m=5.):
        """Контур отеля: тот же OSM-объект, содержащий точку или ближайший ≤ 5 м."""
        point = metric_point(hotel.lat, hotel.lon)
        if hotel.id in self.by_osm_id:
            index, match = self.by_osm_id[hotel.id], 'osm_id'
        else:
            index, match = self.building_at(point.x, point.y), 'contains_hotel_point'
            if index < 0:
                near = [(b['polygon'].distance(point), i) for i, b in enumerate(self.buildings)
                        if b['polygon'].distance(point) <= max_snap_m]
                if not near:
                    return None
                index, match = min(near)[1], 'nearest_within_5m'
        item = self.buildings[index]
        levels, source = None, 'assumed'
        for tags in (item['tags'], hotel.tags):
            try:
                levels = int(float(tags['building:levels']))
                source = 'osm_building_levels'
                break
            except (KeyError, ValueError):
                continue
        if not levels or levels < 1:
            levels, source = ASSUMED_HOTEL_LEVELS, 'assumed_typical_adler'
        return HotelBuilding(item['osm_id'], item['polygon'], min(levels, 40), source, match), index

    def profile(self, x0, y0, normal_azimuth, own_index):
        """Срез поверхности вдоль лучей сектора окна (без высоты наблюдателя)."""
        azimuths = normal_azimuth + np.arange(-WINDOW_HALF_FOV, WINDOW_HALF_FOV+1, 1.)
        rad = np.radians(azimuths)
        X = x0 + np.sin(rad)[:, None] * DISTANCES_M
        Y = y0 + np.cos(rad)[:, None] * DISTANCES_M
        ground = self.dem_grid.bilinear(self.dtm, X, Y)
        row, col, inside = self.dem_grid.index(X, Y)
        sea = self.far_sea[row, col] & inside
        nrow, ncol, ninside = self.near_grid.index(X, Y)
        sea = np.where(ninside, self.near_sea[nrow, ncol], sea)
        brow, bcol, binside = self.bgrid.index(X, Y)
        ids = np.where(binside, self.bid[brow, bcol], -1)
        other = (ids >= 0) & (ids != own_index)  # своё здание не закрывает своё окно
        known = np.where(other, self.bheight[brow, bcol], 0.)
        unknown = other & self.bunknown[brow, bcol]
        ground = np.where(sea, 0., ground)
        return {'azimuths': azimuths, 'ground': ground, 'sea': sea, 'known': known,
                'unknown': unknown, 'building': ids, 'other': other,
                'eye_ground': float(self.dem_grid.bilinear(self.dtm, np.array([x0]), np.array([y0]))[0])}

    def evaluate(self, profile, eye_z, unknown_height):
        """Видимость для одной высоты глаза и одного сценария неизвестных высот."""
        top = profile['ground'] + profile['known'] + profile['unknown'] * unknown_height
        drop = DISTANCES_M**2 / (2*EFFECTIVE_RADIUS_M)
        slope = (top - eye_z - drop) / DISTANCES_M
        slope = np.where(np.isnan(slope), -np.inf, slope)
        running = np.maximum.accumulate(slope, axis=1)
        before = np.concatenate([np.full((slope.shape[0], 1), -np.inf), running[:, :-1]], axis=1)
        visible = slope > before
        sea_rays = (visible & profile['sea']).any(axis=1)
        horizon_index = slope.argmax(axis=1)
        rows = np.arange(slope.shape[0])
        kind = np.where(profile['sea'][rows, horizon_index], 'sea',
                        np.where(profile['other'][rows, horizon_index], 'building', 'terrain'))
        first_sea = np.where(visible & profile['sea'], DISTANCES_M, np.inf).min(axis=1)
        mountain = visible & ~profile['sea'] & ~profile['other'] & (np.nan_to_num(profile['ground']) >= MOUNTAIN_MIN_M)
        return {'sea_rays': sea_rays, 'horizon_deg': np.degrees(np.arctan(running[:, -1])),
                'horizon_kind': kind, 'horizon_building': profile['building'][rows, horizon_index],
                'first_sea_m': first_sea, 'mountain_rays': mountain.any(axis=1),
                'mountain_peak_m': float(np.where(mountain, profile['ground'], 0).max())}


def sunset_months(azimuths, result, tracks):
    """Для каждого месяца: 'sea' — солнце опускается к морскому горизонту,
    'low' — видно ниже 3°, но садится за сушу/дома, 'none' — не видно."""
    status = {}
    lo, hi = azimuths[0], azimuths[-1]
    # Консервативно: просвет должен быть шире 3° (соседние лучи тоже открыты),
    # иначе «закат в щель между домами» зависит от точного места окна.
    horizon = result['horizon_deg']
    widened = np.maximum(horizon, np.maximum(np.r_[horizon[0], horizon[:-1]], np.r_[horizon[1:], horizon[-1]]))
    for month, track in tracks.items():
        best = 'none'
        for sample in track:
            az, alt = sample['azimuth'], sample['altitude']
            # Азимут может переходить через 0/360 относительно нормали фасада.
            az = az + 360 * round((azimuths[len(azimuths)//2] - az) / 360)
            if not lo <= az <= hi or alt > SUNSET_LOW_ALTITUDE:
                continue
            index = int(round(az - lo))
            if alt <= widened[index]:
                continue
            if alt <= SUNSET_SEA_ALTITUDE and result['horizon_kind'][index] == 'sea':
                best = 'sea'
                break
            best = 'low'
        status[month] = best
    return status


def sea_category(share):
    return 'wide' if share >= SEA_WIDE_SHARE else 'partial' if share >= SEA_PARTIAL_SHARE else 'none'


def sunset_category(months):
    return 'none' if not months else 'year_round' if len(months) >= 10 else 'seasonal'


def analyze_hotel(scene: ViewshedScene, hotel, spacing=12., tracks=None):
    """Полный расчёт для отеля во всех сценариях неизвестных высот."""
    match = scene.hotel_building(hotel)
    if match is None:
        return {'status': 'unknown', 'reason': 'hotel_building_not_found'}
    building, own_index = match
    tracks = tracks or monthly_sunset_tracks(hotel.lat, hotel.lon)
    receivers = facade_receivers(building.polygon, heights=(1.,), spacing=spacing, offset=1.)  # z не используется
    # Стена вплотную к соседнему зданию не имеет окон.
    receivers = [r for r in receivers if scene.building_at(r['x'], r['y']) in (-1, own_index)]
    if not receivers:
        return {'status': 'unknown', 'reason': 'no_free_facades', 'building_osm_id': building.osm_id}
    profiles = [scene.profile(r['x'], r['y'], r['azimuth'], own_index) for r in receivers]
    scenarios = {}
    for name, unknown_height in UNKNOWN_HEIGHT_SCENARIOS.items():
        floors = []
        for floor in range(1, building.levels + 1):
            best_sea, best_sun, best_mountain = None, None, None
            for receiver, profile in zip(receivers, profiles):
                eye = profile['eye_ground'] + EYE_ABOVE_FLOOR_M + FLOOR_HEIGHT_M * (floor - 1)
                result = scene.evaluate(profile, eye, unknown_height)
                share = float(result['sea_rays'].mean())
                months = sunset_months(profile['azimuths'], result, tracks)
                visible = [m for m, s in months.items() if s != 'none']
                entry = {'facade': receiver['facade'], 'azimuth': receiver['azimuth'],
                         'lat': round(receiver['lat'], 6), 'lon': round(receiver['lon'], 6),
                         'sea_share': round(share, 3),
                         'nearest_visible_sea_m': (None if not np.isfinite(result['first_sea_m']).any()
                                                   else round(float(result['first_sea_m'].min()))),
                         'mountain_share': round(float(result['mountain_rays'].mean()), 3),
                         'mountain_peak_m': round(result['mountain_peak_m']),
                         'sunset_months': visible,
                         'sunset_over_sea_months': [m for m, s in months.items() if s == 'sea'],
                         'blocking_buildings': sorted({scene.buildings[i]['osm_id'] for i in
                                                       result['horizon_building'][result['horizon_kind'] == 'building']})}
                if best_sea is None or share > best_sea['sea_share']:
                    best_sea = entry
                if best_sun is None or (len(visible), len(entry['sunset_over_sea_months'])) > \
                        (len(best_sun['sunset_months']), len(best_sun['sunset_over_sea_months'])):
                    best_sun = entry
                if best_mountain is None or entry['mountain_share'] > best_mountain['mountain_share']:
                    best_mountain = entry
            floors.append({'floor': floor, 'sea': best_sea, 'sunset': best_sun, 'mountain': best_mountain})
        scenarios[name] = summarize(floors)
    base = scenarios['base']
    robust_by_family = {family: all(s[f'{family}_view_potential'] == base[f'{family}_view_potential']
                                    for s in scenarios.values()) for family in ('sea', 'sunset', 'mountain')}
    robust = all(robust_by_family.values())
    near = shapely.Point(building.polygon.centroid).buffer(300)
    neighbours = [b for b in scene.buildings if b['polygon'].intersects(near) and b['osm_id'] != building.osm_id]
    return {'status': 'computed', 'building_osm_id': building.osm_id, 'building_match': building.match,
            'levels': building.levels, 'levels_source': building.levels_source,
            'receivers': len(receivers), 'robust_to_unknown_heights': robust,
            'robust_by_family': robust_by_family,
            'neighbour_height_coverage_300m': round(sum(b['height'] is not None for b in neighbours)
                                                    / max(1, len(neighbours)), 3),
            'base': base, 'scenarios': {k: {key: v[key] for key in ('sea_view_potential', 'sea_view_min_floor',
                                                                     'sunset_view_potential', 'sunset_view_min_floor',
                                                                     'mountain_view_potential', 'mountain_view_min_floor')}
                                        for k, v in scenarios.items()},
            'inputs': scene.inputs, 'inputs_sha256': scene.fingerprint(),
            'method': {'window_half_fov_deg': WINDOW_HALF_FOV, 'azimuth_step_deg': 1,
                       'max_distance_m': float(DISTANCES_M[-1]), 'floor_height_m': FLOOR_HEIGHT_M,
                       'eye_above_floor_m': EYE_ABOVE_FLOOR_M, 'refraction_k': REFRACTION_K,
                       'unknown_height_scenarios_m': UNKNOWN_HEIGHT_SCENARIOS,
                       'sea_partial_share': SEA_PARTIAL_SHARE, 'sea_wide_share': SEA_WIDE_SHARE,
                       'sunset_low_altitude_deg': SUNSET_LOW_ALTITUDE, 'receiver_spacing_m': spacing,
                       'sun': 'NOAA solar position, 15-е число месяца'},
            'limits': LIMITS + (['hotel_levels_assumed'] if building.levels_source.startswith('assumed') else [])}


def summarize(floors):
    """Сводка по этажам: минимальный этаж и лучшая точка для текста объяснения."""
    sea_floors = [f for f in floors if f['sea']['sea_share'] >= SEA_PARTIAL_SHARE]
    sun_floors = [f for f in floors if f['sunset']['sunset_months']]
    mountain_floors = [f for f in floors if f['mountain']['mountain_share'] >= SEA_PARTIAL_SHARE]
    best_mountain = max((f['mountain'] | {'floor': f['floor']} for f in floors),
                        key=lambda x: (x['mountain_share'], -x['floor']))
    best_sea = max((f['sea'] | {'floor': f['floor']} for f in floors), key=lambda x: (x['sea_share'], -x['floor']))
    best_sun = max((f['sunset'] | {'floor': f['floor']} for f in floors),
                   key=lambda x: (len(x['sunset_months']), len(x['sunset_over_sea_months']), -x['floor']))
    result = {
        'sea_view_potential': sea_category(best_sea['sea_share']),
        'sea_view_min_floor': sea_floors[0]['floor'] if sea_floors else None,
        'sunset_view_potential': sunset_category(best_sun['sunset_months']),
        'sunset_view_min_floor': sun_floors[0]['floor'] if sun_floors else None,
        'mountain_view_potential': sea_category(best_mountain['mountain_share']),
        'mountain_view_min_floor': mountain_floors[0]['floor'] if mountain_floors else None,
        'best_sea': best_sea, 'best_sunset': best_sun, 'best_mountain': best_mountain,
        'floors': [{'floor': f['floor'], 'sea_share': f['sea']['sea_share'],
                    'sea_facade_azimuth': f['sea']['azimuth'], 'sunset_months': f['sunset']['sunset_months'],
                    'sunset_over_sea_months': f['sunset']['sunset_over_sea_months'],
                    'sunset_facade_azimuth': f['sunset']['azimuth'], 'mountain_share': f['mountain']['mountain_share'],
                    'mountain_facade_azimuth': f['mountain']['azimuth']} for f in floors],
    }
    result['summary_sea'], result['summary_sunset'] = explain(result)
    result['summary_mountain'] = explain_mountain(result)
    result['summary'] = result['summary_sea'] + ' ' + result['summary_sunset']
    return result


def explain_mountain(summary):
    best = summary['best_mountain']
    if summary['mountain_view_min_floor'] is None:
        return 'Гор выше 300 м из окон не видно (по модели).'
    width = 'широкий вид' if summary['mountain_view_potential'] == 'wide' else 'горы в просвете'
    return (f'Горы: {width} из окон стороны {compass(best["azimuth"])}, с {summary["mountain_view_min_floor"]}-го этажа; '
            f'лучше всего на {best["floor"]}-м ({best["mountain_share"]*100:.0f}% обзора окна, видны вершины до ≈ {best["mountain_peak_m"]} м).')


def explain(summary):
    """Тексты (море, закат): «закат из окон стороны З, с 5-го этажа, апрель–август»."""
    parts = []
    sea = summary['best_sea']
    if summary['sea_view_min_floor'] is None:
        parts.append('Моря из окон не видно ни с одного этажа (по модели).')
    else:
        width = 'широкий вид' if summary['sea_view_potential'] == 'wide' else 'море в просвете'
        parts.append(f'Море: {width} из окон стороны {compass(sea["azimuth"])} (азимут {sea["azimuth"]:.0f}°), '
                     f'с {summary["sea_view_min_floor"]}-го этажа; лучше всего на {sea["floor"]}-м '
                     f'({sea["sea_share"]*100:.0f}% обзора окна).')
    sun = summary['best_sunset']
    if summary['sunset_view_min_floor'] is None:
        parts.append('Заката из окон не видно (по модели).')
    else:
        text = (f'Закат из окон стороны {compass(sun["azimuth"])}, с {summary["sunset_view_min_floor"]}-го этажа, '
                f'{month_ranges(sun["sunset_months"])}')
        if sun['sunset_over_sea_months']:
            text += f'; солнце садится в море: {month_ranges(sun["sunset_over_sea_months"])}'
        parts.append(text + '.')
    return parts[0], parts[1]
