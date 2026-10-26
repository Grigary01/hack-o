from types import SimpleNamespace
from shapely.geometry import LineString
from app.geo.aircraft import exposure, runway_ends
from app.geo.geometry import PROJECT, UNPROJECT


def runway_at(lat, lon, length=2000):
    """ВПП с востока на запад; западный торец в (lat, lon)."""
    x, y = PROJECT(lon, lat)
    return {'osm_id': 'osm:way:1', 'ref': '09/27', 'line': LineString([(x, y), (x + length, y)])}, x, y


def test_point_under_approach_is_high_and_aircraft_is_low():
    runway, x, y = runway_at(43.44, 39.93)
    lon, lat = UNPROJECT(x - 1000, y)  # 1 км к западу, прямо на продолжении оси
    category, details = exposure(lat, lon, [runway], lambda *_: 0.)
    nearest = details['nearest']
    assert category == 'high' and nearest['kind'] == 'extended_centerline' and nearest['landing_heading'] == 90
    # Глиссада 3°: на 1 км от порога самолёт на ~15 + 52 = 67 м, наблюдатель на 10 м.
    assert 50 < nearest['slant_m'] < 70


def test_far_side_point_is_low_and_ends_point_outward():
    runway, x, y = runway_at(43.44, 39.93)
    west, east = runway_ends(runway)
    assert west['ux'] < 0 and east['ux'] > 0
    lon, lat = UNPROJECT(x + 1000, y + 3000)  # 3 км вбок от середины ВПП
    category, details = exposure(lat, lon, [runway], lambda *_: 0.)
    assert category == 'low' and details['nearest']['slant_m'] > 2000
    assert exposure(lat, lon, [], lambda *_: 0.)[0] is None
