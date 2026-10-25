"""Путь по рёбрам OSM walking graph. Никакого geodesic fallback.

Входы не гарантированы: центроид отеля и кандидат прохода привязываются
к графу. Эти отрезки учитываются отдельно, помечаются как оценочные.
"""
from dataclasses import dataclass, field
from pathlib import Path
import networkx as nx
from shapely.geometry import LineString
from shapely.ops import nearest_points
from app.geo.geometry import metric_point, element_shape, UNPROJECT
from app.geo.osm_provider import osm_id


@dataclass
class RouteResult:
    distance_m: float | None
    reason: str | None = None
    network_distance_m: float | None = None
    connector_distance_m: float = 0
    coordinates: list = field(default_factory=list)
    way_ids: list = field(default_factory=list)
    beach_id: str | None = None
    beach_name: str | None = None
    flags: list[str] = field(default_factory=list)


def blocked(tags):
    """Запрет foot сильнее общего доступа; явный foot=yes разрешает private access."""
    if tags.get('foot') in ('no','private'):
        return True
    if tags.get('access') in ('no','private') and tags.get('foot') not in ('yes','designated','permissive'):
        return True
    if tags.get('foot:conditional') or tags.get('access:conditional'):
        return True  # без движка условий не обещаем доступ
    barrier = tags.get('barrier')
    if barrier and barrier not in ('bollard','kerb','entrance','cattle_grid'):
        return tags.get('foot') not in ('yes','designated','permissive')
    return False


def load_walking_graph(path: Path):
    graph = nx.read_graphml(path, node_type=int, force_multigraph=True)
    # OSMnx выгружает length, x, y; преобразуем явно, без зависимости от OSMnx в runtime.
    for _, node in graph.nodes(data=True):
        node['x'], node['y'] = float(node['x']), float(node['y'])
    graph.remove_nodes_from([n for n, tags in graph.nodes(data=True) if blocked(tags)])
    for u, v, key, tags in list(graph.edges(keys=True, data=True)):
        if blocked(tags) or tags.get('highway') in ('motorway','motorway_link','construction','proposed'):
            graph.remove_edge(u,v,key)
        else:
            tags['length'] = float(tags['length'])
            # Walk graph OSMnx по умолчанию двунаправлен. Явный oneway:foot учитываем отдельно.
            reverse = str(tags.get('reversed', False)).lower() == 'true'
            foot_oneway = tags.get('oneway:foot')
            if (foot_oneway in ('yes','1') and reverse) or (foot_oneway == '-1' and not reverse):
                graph.remove_edge(u,v,key)
    graph.remove_nodes_from(list(nx.isolates(graph)))
    return graph


class PedestrianRouter:
    def __init__(self, graph, beaches, barriers=(), max_snap_m=80, max_beach_snap_m=30):
        self.graph = graph
        self.max_snap_m = max_snap_m
        self.points = {n: metric_point(d['y'],d['x']) for n,d in graph.nodes(data=True)}
        self.barriers = [shape for item in barriers if blocked(item.get('tags',{}))
                         and (shape := element_shape(item)) is not None]
        self.targets = []
        for beach in beaches:
            if blocked(beach.get('tags',{})):
                continue
            shape = element_shape(beach, polygon=True)
            if shape is None:
                continue
            for node, point in self.points.items():
                # Существующая пешая дорожка на/у пляжа, не ближайшая вода за забором.
                incident = list(graph.edges(node, data=True))
                if not any(d.get('highway') in ('footway','path','pedestrian','steps') for _,_,d in incident):
                    continue
                distance = point.distance(shape)
                if distance <= max_beach_snap_m:
                    target = nearest_points(point, shape)[1]
                    if not self._connector_blocked(point, target):
                        self.targets.append({'node': node, 'connector': distance,
                                             'point': target, 'beach_id': osm_id(beach),
                                             'name': beach.get('tags',{}).get('name','Пляж OSM')})

    def _connector_blocked(self, a, b):
        if a.equals(b):
            return False
        line = LineString([a,b])
        return any(line.intersects(shape.buffer(.5)) for shape in self.barriers)

    def distance_to_beach(self, hotel) -> RouteResult:
        if not self.points or not self.targets:
            return RouteResult(None, reason='no_accessible_beach_target')
        origin = metric_point(hotel.lat, hotel.lon)
        # Только ближайший узел: не прыгаем к дальнему через препятствие при no path.
        start = min(self.points, key=lambda n: origin.distance(self.points[n]))
        start_gap = origin.distance(self.points[start])
        if start_gap > self.max_snap_m:
            return RouteResult(None, reason='hotel_too_far_from_graph')
        if self._connector_blocked(origin, self.points[start]):
            return RouteResult(None, reason='hotel_connector_crosses_barrier')
        lengths, paths = nx.single_source_dijkstra(self.graph, start, weight='length')
        reachable = [t for t in self.targets if t['node'] in lengths]
        if not reachable:
            return RouteResult(None, reason='no_path')
        target = min(reachable, key=lambda t: lengths[t['node']]+t['connector'])
        route = paths[target['node']]
        way_ids = []
        for u,v in zip(route,route[1:]):
            edge = min(self.graph[u][v].values(), key=lambda e: e['length'])
            way_ids.append(str(edge.get('osmid','unknown')))
        lon, lat = UNPROJECT(target['point'].x,target['point'].y)
        coords = [[hotel.lon,hotel.lat]] + [[self.graph.nodes[n]['x'],self.graph.nodes[n]['y']] for n in route] + [[lon,lat]]
        connectors = start_gap + target['connector']
        return RouteResult(lengths[target['node']] + connectors,
                           network_distance_m=lengths[target['node']], connector_distance_m=connectors,
                           coordinates=coords, way_ids=list(dict.fromkeys(way_ids)),
                           beach_id=target['beach_id'], beach_name=target['name'],
                           flags=['hotel_entry_approximate','beach_access_candidate',
                                  'connectors_not_surveyed','osm_access_incomplete',
                                  'terrain_and_crossing_safety_not_assessed'])
