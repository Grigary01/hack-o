import json
from types import SimpleNamespace
import networkx as nx
import pytest
from app.geo.geometry import geodesic_distance_m
from app.geo.routing import PedestrianRouter, blocked, load_walking_graph
from app.geo.osm_provider import fetch_snapshot, make_query


def toy_graph():
    graph=nx.MultiDiGraph()
    points={1:(43.43,39.92),2:(43.432,39.92),3:(43.432,39.922),4:(43.43,39.922)}
    for node,(lat,lon) in points.items():
        graph.add_node(node,x=lon,y=lat)
    for u,v in [(1,2),(2,3),(3,4)]:
        length=geodesic_distance_m(points[u],points[v])
        graph.add_edge(u,v,length=length,highway='footway',osmid=str(u))
        graph.add_edge(v,u,length=length,highway='footway',osmid=str(u))
    beach={'type':'way','id':999,'tags':{'natural':'beach'},'geometry':[
        {'lat':43.42999,'lon':39.92199},{'lat':43.43001,'lon':39.92199},
        {'lat':43.43001,'lon':39.92201},{'lat':43.42999,'lon':39.92201},
        {'lat':43.42999,'lon':39.92199}]}
    return graph,beach


def test_route_follows_detour_instead_of_geodesic():
    graph,beach=toy_graph()
    result=PedestrianRouter(graph,[beach],max_beach_snap_m=1).distance_to_beach(SimpleNamespace(lat=43.43,lon=39.92))
    direct=geodesic_distance_m((43.43,39.92),(43.43,39.922))
    assert result.distance_m>direct*3
    assert result.network_distance_m==pytest.approx(sum(graph[u][v][0]['length'] for u,v in [(1,2),(2,3),(3,4)]))
    assert result.coordinates[0]==[39.92,43.43]


def test_no_path_and_missing_targets_are_unknown():
    graph,beach=toy_graph()
    graph.remove_edge(2,3)
    result=PedestrianRouter(graph,[beach],max_beach_snap_m=1).distance_to_beach(SimpleNamespace(lat=43.43,lon=39.92))
    assert result.distance_m is None and result.reason=='no_path'
    assert PedestrianRouter(graph,[]).distance_to_beach(SimpleNamespace(lat=43.43,lon=39.92)).distance_m is None


def test_snap_gap_and_barrier_do_not_fake_route():
    graph,beach=toy_graph()
    far=PedestrianRouter(graph,[beach],max_snap_m=2).distance_to_beach(SimpleNamespace(lat=43.429,lon=39.92))
    assert far.reason=='hotel_too_far_from_graph'
    barrier={'type':'way','id':111,'tags':{'barrier':'fence'},'geometry':[
        {'lat':43.42995,'lon':39.9199},{'lat':43.42995,'lon':39.9201}]}
    result=PedestrianRouter(graph,[beach],[barrier]).distance_to_beach(SimpleNamespace(lat=43.4299,lon=39.92))
    assert result.reason=='hotel_connector_crosses_barrier'


def test_private_access_and_foot_override():
    assert blocked({'access':'private'})
    assert blocked({'foot':'no','access':'yes'})
    assert not blocked({'access':'private','foot':'yes'})
    assert blocked({'barrier':'gate'})
    assert blocked({'foot:conditional':'yes @ (Mo-Fr)'})


def test_partial_overpass_response_is_not_success(tmp_path,monkeypatch):
    import httpx
    monkeypatch.setattr('app.geo.osm_provider.time.sleep',lambda _:None)
    calls=[]
    def partial(*a,**kw):
        calls.append(1)
        return httpx.Response(200,json={'elements':[{'id':1}],'remark':'runtime error'},request=httpx.Request('POST','https://example.org'))
    monkeypatch.setattr('app.geo.osm_provider.httpx.post',partial)
    with pytest.raises(ValueError,match='Неполная'):
        fetch_snapshot('https://example.org',make_query([43.4,39.9,43.5,40]),tmp_path/'snapshot.json')
    assert len(calls)==3 and not (tmp_path/'snapshot.json').exists()


def test_graph_loader_removes_private_edges(tmp_path):
    graph,beach=toy_graph()
    graph[2][3][0]['access']='private'
    path=tmp_path/'graph.graphml'
    nx.write_graphml(graph,path)
    safe=load_walking_graph(path)
    assert not safe.has_edge(2,3)


def test_outline_fallback_reaches_network_but_not_through_buildings(monkeypatch):
    from shapely.geometry import box
    from app.geo.geometry import PROJECT
    graph, beach = toy_graph()
    hotel = SimpleNamespace(lat=43.4285, lon=39.92)  # ~170 м южнее узла 1: точка слишком далеко
    router = PedestrianRouter(graph, [beach], max_beach_snap_m=1, max_snap_m=80)
    assert router.distance_to_beach(hotel).reason == 'hotel_too_far_from_graph'
    x, y = PROJECT(39.92, 43.4285)
    outline = box(x - 10, y - 10, x + 10, y + 110)  # длинное здание почти до узла 1
    monkeypatch.setattr('app.geo.routing.MIN_COMPONENT_NODES', 1)  # в игрушечном графе 4 узла
    result = router.distance_to_beach(hotel, outline, [])
    assert result.distance_m is not None and 'start_from_building_outline' in result.flags
    blocker = box(x - 30, y + 112, x + 30, y + 140)  # чужой дом между стеной и сетью
    assert router.distance_to_beach(hotel, outline, [blocker]).distance_m is None
