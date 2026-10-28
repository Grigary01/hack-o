from shapely.geometry import box
from app.geo.facade_noise import side_risks, summarize, explain
from app.geo.geometry import PROJECT, UNPROJECT

LAT, LON = 43.43, 39.92


def road_north_of(y_offset):
    x, y = PROJECT(LON, LAT)
    a, b = UNPROJECT(x - 300, y + y_offset), UNPROJECT(x + 300, y + y_offset)
    return {'type': 'way', 'id': 1, 'tags': {'highway': 'primary', 'name': 'улица Ленина'},
            'geometry': [{'lon': a[0], 'lat': a[1]}, {'lon': b[0], 'lat': b[1]}]}


def test_street_side_loud_courtyard_side_quiet_and_shielded():
    x, y = PROJECT(LON, LAT)
    building = box(x - 15, y - 10, x + 15, y + 10)
    sides = side_risks(building, [road_north_of(25)], [])
    summary = summarize(sides)
    assert summary['loud_side'] == 'С' and summary['quiet_side'] == 'Ю'
    assert sides['Ю']['shielded'] == 'своё здание' and summary['quiet_category'] == 'high'
    assert summary['loud_category'] in ('low', 'medium') and 'Тихая сторона — Ю' in explain(summary)


def test_neighbour_building_partially_shields():
    x, y = PROJECT(LON, LAT)
    building = box(x - 15, y - 10, x + 15, y + 10)
    open_ = side_risks(building, [road_north_of(40)], [])['С']['risk']
    neighbour = box(x - 40, y + 15, x + 40, y + 30)
    shielded = side_risks(building, [road_north_of(40)], [neighbour])['С']
    assert shielded['shielded'] == 'соседний дом' and shielded['risk'] < open_
