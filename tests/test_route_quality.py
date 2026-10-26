from types import SimpleNamespace
import networkx as nx
from app.geo.geometry import PROJECT, UNPROJECT
from app.geo.route_quality import analyze, climb, explain_crossings

LAT, LON = 43.43, 39.92


def test_climb_ignores_dem_noise_below_hysteresis():
    assert climb([5, 5.4, 4.8, 5.3, 5.1]) == (0., 0.)
    assert climb([5, 7, 9, 8.5, 12, 4]) == (7., 8.)


def toy(bridge=None):
    """Путь с запада на восток 200 м; улица Ленина идёт с юга на север посередине."""
    x, y = PROJECT(LON, LAT)
    graph = nx.MultiDiGraph()
    for i, dx in enumerate((0, 100, 200)):
        lon, lat = UNPROJECT(x + dx, y)
        graph.add_node(i, x=lon, y=lat)
    graph.add_edge(0, 1, length=100., highway='footway', osmid='10', **({'bridge': bridge} if bridge else {}))
    graph.add_edge(1, 2, length=100., highway='steps', osmid='11')
    road = {'type': 'way', 'id': 77, 'tags': {'highway': 'primary', 'name': 'улица Ленина'},
            'geometry': [{'lon': UNPROJECT(x + 50, y + s)[0], 'lat': UNPROJECT(x + 50, y + s)[1]} for s in (-300, 300)]}
    crossing = {'type': 'node', 'id': 5, 'tags': {'highway': 'crossing', 'crossing': 'traffic_signals'},
                'lon': UNPROJECT(x + 52, y)[0], 'lat': UNPROJECT(x + 52, y)[1]}
    route = SimpleNamespace(distance_m=200., node_ids=[0, 1, 2], reason=None)
    return graph, [road, crossing], route


def test_at_grade_crossing_type_and_stairs():
    graph, elements, route = toy()
    result = analyze(route, graph, elements, lambda x, y: 5.)
    assert result['busy_crossings'] == 1 and result['crossings'][0]['crossing'] == 'светофор'
    assert result['stairs_segments'] == 1 and result['climb_m'] == 0
    assert 'улица Ленина (светофор)' in explain_crossings(result)


def test_footbridge_is_not_a_crossing_and_beachfront_is_zero():
    graph, elements, route = toy(bridge='yes')
    assert analyze(route, graph, elements, lambda x, y: 5.)['busy_crossings'] == 0
    beachfront = SimpleNamespace(distance_m=40., node_ids=[0], reason=None)
    assert analyze(beachfront, graph, elements, lambda x, y: 5.)['climb_m'] == 0
    assert analyze(SimpleNamespace(distance_m=None, node_ids=[], reason='no_path'), graph, elements, None) is None
