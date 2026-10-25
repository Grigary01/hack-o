"""Локальная метрическая проекция для Адлера; порядок координат всегда lon, lat."""
from pyproj import Geod, Transformer
from shapely.geometry import Point, LineString, Polygon
from shapely import transform

PROJECT = Transformer.from_crs('EPSG:4326', 'EPSG:32637', always_xy=True).transform
UNPROJECT = Transformer.from_crs('EPSG:32637', 'EPSG:4326', always_xy=True).transform
GEOD = Geod(ellps='WGS84')


def geodesic_distance_m(a, b):
    """a,b: (lat,lon). Только диагностика/привязка, не пеший маршрут."""
    return GEOD.inv(a[1], a[0], b[1], b[0])[2]


def metric_point(lat, lon):
    return Point(*PROJECT(lon, lat))


def element_shape(element, polygon=False):
    points = [(p['lon'], p['lat']) for p in element.get('geometry', []) if p]
    if len(points) >= 3 and polygon:
        geometry = Polygon(points)
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
    elif len(points) >= 2:
        geometry = LineString(points)
    elif 'lon' in element:
        geometry = Point(element['lon'], element['lat'])
    else:
        return None
    return transform(geometry, PROJECT, interleaved=False)
