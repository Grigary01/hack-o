"""OSM ingestion: union запросов, тип+ID, JSON cache и явные ошибки.

Адаптировано из OSMSearchEngine._execute_poi_search/_get_cache_key
(Maxim, MIT). Убраны pickle, скрытый fallback на Москву и пустой успех.
"""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx

CATEGORY_FILTERS = {
    'hotels': '["tourism"~"^(hotel|guest_house|hostel)$"]',
    'beaches': '["natural"="beach"]',
    'nightlife': '["amenity"~"^(bar|pub|nightclub)$"]',
    'cafes': '["amenity"="cafe"]',
    'roads': '["highway"]',
    'rail': '["railway"="rail"]',
    'barriers': '["barrier"]',
}


def make_query(bbox: list[float]) -> str:
    south, west, north, east = bbox
    if not (-90 < south < north < 90 and -180 < west < east < 180):
        raise ValueError('Некорректный bbox')
    area = f'({south},{west},{north},{east})'
    parts = [f'nwr{tags}{area};' for tags in CATEGORY_FILTERS.values()]
    return '[out:json][timeout:90];(' + ''.join(parts) + ');out body geom;'


def fetch_snapshot(endpoint: str, query: str, target: Path, refresh=False) -> dict:
    """Два bounded retry, cache по хешу запроса; remark означает неполный ответ."""
    digest = hashlib.sha256(query.encode()).hexdigest()
    if target.exists() and not refresh:
        cached = json.loads(target.read_text())
        if cached['metadata']['query_sha256'] == digest:
            return cached
    for attempt in range(3):
        try:
            response = httpx.post(endpoint, data={'data': query}, timeout=120,
                                  headers={'User-Agent': 'AdlerHackathonPrototype/0.1'})
            response.raise_for_status()
            raw = response.json()
            if raw.get('remark') or not raw.get('elements'):
                raise ValueError(f'Неполная выгрузка OSM: {raw.get("remark", "empty")}')
            snapshot = {'metadata': {
                'endpoint': endpoint, 'query': query, 'query_sha256': digest,
                'collected_at': datetime.now(timezone.utc).isoformat(),
                'osm_base': raw.get('osm3s', {}).get('timestamp_osm_base'),
                'license': 'ODbL-1.0', 'attribution': '© OpenStreetMap contributors',
            }, 'elements': raw['elements']}
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_suffix('.tmp')
            temp.write_text(json.dumps(snapshot, ensure_ascii=False))
            temp.replace(target)
            return snapshot
        except (httpx.HTTPError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError('unreachable')


def osm_id(element: dict) -> str:
    return f'osm:{element["type"]}:{element["id"]}'


def coordinates(element: dict) -> tuple[float, float] | None:
    if 'lat' in element:
        return element['lat'], element['lon']
    geometry = element.get('geometry', [])
    if not geometry:
        geometry = [p for m in element.get('members', []) for p in m.get('geometry', [])]
    if geometry:
        # Центр bbox — точка отеля, НЕ подтверждённый вход.
        return ((min(p['lat'] for p in geometry) + max(p['lat'] for p in geometry)) / 2,
                (min(p['lon'] for p in geometry) + max(p['lon'] for p in geometry)) / 2)
    return None


def fetch_osm_hotels(snapshot: dict, region: dict) -> list[dict]:
    s, w, n, e = region['hotel_bbox_south_west_north_east']
    hotels = []
    for item in snapshot['elements']:
        tags = item.get('tags', {})
        point = coordinates(item)
        if tags.get('tourism') != 'hotel' or not tags.get('name') or point is None:
            continue
        lat, lon = point
        if s <= lat <= n and w <= lon <= e:
            hotels.append({'id': osm_id(item), 'name': tags['name'], 'lat': lat, 'lon': lon,
                           'tags': tags, 'source_url': f'https://www.openstreetmap.org/{item["type"]}/{item["id"]}',
                           'collected_at': snapshot['metadata']['collected_at'], 'region': region['id']})
    # Детерминированная выборка, node/way дубли одного имени и точки удалены.
    unique = []
    for h in sorted(hotels, key=lambda x: x['id']):
        if not any(h['name'].casefold() == u['name'].casefold() and
                   abs(h['lat']-u['lat']) < .001 and abs(h['lon']-u['lon']) < .001 for u in unique):
            unique.append(h)
    return unique[:region['hotel_limit']]


def fetch_osm_pois(snapshot: dict, category: str) -> list[dict]:
    tests = {
        'beaches': lambda t: t.get('natural') == 'beach',
        'nightlife': lambda t: t.get('amenity') in ('bar','pub','nightclub'),
        'cafes': lambda t: t.get('amenity') == 'cafe',
        'roads': lambda t: 'highway' in t,
        'rail': lambda t: t.get('railway') == 'rail',
        'barriers': lambda t: 'barrier' in t,
    }
    if category not in tests:
        raise ValueError('Неподдерживаемая категория POI')
    return [x for x in snapshot['elements'] if tests[category](x.get('tags', {}))]
