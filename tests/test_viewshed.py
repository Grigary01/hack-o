from datetime import date, datetime, timezone
from types import SimpleNamespace
import numpy as np
import pytest
from shapely.geometry import box, Point
from app.geo.geometry import PROJECT, UNPROJECT
from app.geo.solar import sun_position, sunset_track
from app.geo.viewshed import Grid, ViewshedScene, analyze_hotel, building_height, month_ranges, sea_polygon

LAT, LON = 43.435, 39.92


def test_sun_matches_known_geometry_for_adler():
    # Полдень летнего солнцестояния: 90 - 43.435 + 23.44 ≈ 70°.
    noon = max(sun_position(datetime(2026, 6, 21, 9, m, tzinfo=timezone.utc), LAT, LON)[1] for m in range(60))
    assert noon == pytest.approx(70.0, abs=0.1)
    june, december = sunset_track(date(2026, 6, 21), LAT, LON), sunset_track(date(2026, 12, 21), LAT, LON)
    # Летом солнце садится на северо-западе, зимой на юго-западе.
    assert 302 < june[-1]['azimuth'] < 306 and 236 < december[-1]['azimuth'] < 240
    # Заход около 20:05 МСК летом и 16:45 МСК зимой.
    assert june[-1]['utc'][11:13] == '17' and december[-1]['utc'][11:13] == '13'


def test_month_ranges_and_heights():
    assert month_ranges([4, 5, 6, 7, 8]) == 'апрель–август'
    assert month_ranges([1, 2, 11, 12]) == 'ноябрь–февраль'
    assert month_ranges([3, 10]) == 'март, октябрь'
    assert month_ranges(list(range(1, 13))) == 'круглый год'
    assert building_height({'building': 'yes', 'building:levels': '5'}) == (15.0, 'osm_levels')
    assert building_height({'building': 'yes', 'height': '12 m'}) == (12.0, 'osm_height')
    assert building_height({'building': 'yes'}) == (None, 'missing')


def test_sea_is_right_of_coastline_direction():
    x, y = PROJECT(LON, LAT)
    # Линия идёт на север: по правилу OSM суша слева (запад), море справа (восток).
    north = [UNPROJECT(x, y - 1500), UNPROJECT(x, y + 1500)]
    coast = [{'type': 'way', 'id': 1, 'tags': {'natural': 'coastline'},
              'geometry': [{'lon': lon, 'lat': lat} for lon, lat in north]}]
    sea = sea_polygon(coast, (x - 1000, y - 1000, x + 1000, y + 1000))
    assert sea.contains(Point(x + 300, y)) and not sea.contains(Point(x - 300, y))
    with pytest.raises(ValueError):
        sea_polygon(coast, (x - 3000, y - 3000, x + 3000, y + 3000))  # линия не делит рамку


def synthetic_scene(wall_height):
    """Ровная суша 5 м, море западнее 200 м в полосе ±3 км, стена 6 км на 40–60 м к западу."""
    hx, hy = PROJECT(LON, LAT)
    dem_grid = Grid(hx - 25000, hy - 25000, 30., (1667, 1667))
    near_grid = Grid(hx - 3000, hy - 3000, 10., (600, 600))

    def sea_mask(grid):
        xs, ys = grid.centers()
        return (xs < hx - 200) & (np.abs(ys - hy) < 3000)

    buildings = [
        {'osm_id': 'osm:way:1', 'polygon': box(hx - 10, hy - 10, hx + 10, hy + 10), 'height': 9.,
         'method': 'osm_levels', 'tags': {'building': 'hotel', 'building:levels': '3'}},
        {'osm_id': 'osm:way:2', 'polygon': box(hx - 60, hy - 3000, hx - 40, hy + 3000), 'height': wall_height,
         'method': 'osm_height', 'tags': {'building': 'yes'}},
    ]
    bgrid = Grid(hx - 3200, hy - 3200, 4., (1600, 1600))
    bheight = np.zeros(bgrid.shape, np.float32)
    bid = np.full(bgrid.shape, -1, np.int32)
    for i, b in enumerate(buildings):
        bgrid.rasterize(b['polygon'], bid, i)
        bgrid.rasterize(b['polygon'], bheight, b['height'])
    dtm = np.full(dem_grid.shape, 5., np.float32)
    return ViewshedScene(dem_grid, dtm, sea_mask(dem_grid), near_grid, sea_mask(near_grid), bgrid, bheight,
                         np.zeros(bgrid.shape, bool), bid, buildings, {'synthetic': True},
                         {'osm:way:1': 0, 'osm:way:2': 1})


def hotel():
    return SimpleNamespace(id='osm:way:1', lat=LAT, lon=LON, tags={})


def test_wall_hides_sea_from_low_floors_only():
    # Стена 6 м на земле 5 м: верх 11 м. Глаза: 6.6 / 9.6 / 12.6 м.
    # С 3-го этажа луч проходит над стеной и видит дальнее море.
    result = analyze_hotel(synthetic_scene(6.), hotel())
    base = result['base']
    assert result['status'] == 'computed' and result['robust_to_unknown_heights']
    assert base['sea_view_min_floor'] == 3 and base['sea_view_potential'] != 'none'
    assert [f['sea_share'] for f in base['floors']][:2] == [0, 0]
    assert 'osm:way:2' in base['best_sea']['blocking_buildings'] or base['floors'][0]['sea_share'] == 0
    # Со 2-го этажа горизонт над стеной ~2°: низкое солнце (2–3°) уже видно, морского заката нет.
    assert base['sunset_view_min_floor'] == 2
    floor3 = base['floors'][2]
    assert floor3['sunset_over_sea_months'] and 'стороны З' in base['summary']


def test_tall_wall_blocks_everything_and_low_wall_opens_first_floor():
    tall = analyze_hotel(synthetic_scene(30.), hotel())['base']
    assert tall['sea_view_potential'] == 'none' and tall['sea_view_min_floor'] is None
    assert tall['sunset_view_min_floor'] is None
    low = analyze_hotel(synthetic_scene(1.), hotel())['base']
    assert low['sea_view_min_floor'] == 1


def test_ridge_to_the_east_gives_mountain_view_with_peak_height():
    scene = synthetic_scene(6.)
    xs, _ = scene.dem_grid.centers()
    hx, _ = PROJECT(LON, LAT)
    scene.dtm[(xs > hx + 8000) & (xs < hx + 12000)] = 800.  # хребет 800 м в 8–12 км к востоку
    base = analyze_hotel(scene, hotel())['base']
    assert base['mountain_view_potential'] != 'none' and base['mountain_view_min_floor'] == 1
    assert base['best_mountain']['mountain_peak_m'] == 800 and 'стороны В' in base['summary_mountain']
    assert analyze_hotel(synthetic_scene(6.), hotel())['base']['mountain_view_potential'] == 'none'


def test_photo_verified_levels_override_osm_and_trees_block_low_floors():
    scene = synthetic_scene(1.)
    scene.levels_verified = {'osm:way:1': {'levels': 5, 'certainty': 'exact'}}
    result = analyze_hotel(scene, hotel())
    assert result['levels'] == 5 and result['levels_source'] == 'photo_verified'
    # Полоса деревьев 10 м (в базовом сценарии 0.6 → 6 м, верх 11 м) закрывает 1–2 этажи, но не 3-й (глаза 12.6 м).
    trees = synthetic_scene(1.)
    hx, hy = PROJECT(LON, LAT)
    xs, ys = trees.bgrid.centers()
    trees.trees = np.where((xs > hx - 120) & (xs < hx - 100), 10., 0.).astype(np.float32)
    base = analyze_hotel(trees, hotel())['base']
    assert base['sea_view_min_floor'] == 3 and base['vegetation_horizon_share_floor1'] > 0.3
