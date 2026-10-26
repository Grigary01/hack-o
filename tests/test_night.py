from types import SimpleNamespace
import pytest
from app.geo.geometry import PROJECT, UNPROJECT
from app.geo.night import night_status, summarize, weekly_schedule, open_at


@pytest.mark.parametrize('hours, status', [
    ('24/7', '24/7'),
    ('Mo-Su 17:00-03:00', 'night'),          # через полночь
    ('Mo-Su 10:00-01:00', 'not_night'),      # закрывается ровно в 01:00
    ('00:00-03:00,04:00-24:00', 'night'),
    ('Mo-Fr 18:00-04:00; Sa-Su off', 'not_night'),
    ('Mo-Su 18:00-04:00; Su off', 'not_night'),   # хвост субботы покрывает 01:00 вс, но пн 01:00 — хвост закрытого вс
    ('PH,Mo-Su 09:00-21:00', 'unknown'),      # праздники не разбираем — не угадываем
    ('sunrise-sunset', 'unknown'),
    (None, 'unknown'),
])
def test_night_status(hours, status):
    assert night_status(hours) == status


def test_later_rule_overrides_day_and_overnight_tail():
    schedule = weekly_schedule('Mo-Su 09:00-21:00; Fr 09:00-02:00')
    assert open_at(schedule, 5, 90)       # суббота 01:30 — хвост пятницы
    assert not open_at(schedule, 4, 90)   # пятница 01:30 — хвост четверга закрыт


def test_summary_counts_only_known_night_places_within_radius():
    lat, lon = 43.43, 39.92
    x, y = PROJECT(lon, lat)
    def place(dx, tags):
        plon, plat = UNPROJECT(x + dx, y)
        return {'type': 'node', 'id': dx, 'lat': plat, 'lon': plon, 'tags': tags}
    elements = [place(100, {'amenity': 'pharmacy', 'opening_hours': '24/7'}),
                place(200, {'shop': 'convenience', 'opening_hours': 'Mo-Su 08:00-22:00'}),
                place(300, {'amenity': 'cafe'}),
                place(900, {'amenity': 'fuel', 'opening_hours': '24/7'})]
    summary = summarize(SimpleNamespace(lat=lat, lon=lon), elements)
    assert summary['night_count'] == 1 and summary['unknown_hours_in_radius'] == 1
    assert summary['nearest_night_pharmacy']['distance_m'] == 100
