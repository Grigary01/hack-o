"""Online-команда. Не вызывается сервером; повторный запуск использует snapshot."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from app.core.config import settings
from app.geo.osm_provider import fetch_snapshot, make_query, fetch_osm_hotels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    root = settings.demo_dir
    region = json.loads((root / 'region.json').read_text())
    snapshot = fetch_snapshot(settings.overpass_url,
                              make_query(region['bbox_south_west_north_east']),
                              root / 'osm_snapshot.json', args.refresh)
    hotels = fetch_osm_hotels(snapshot, region)
    if len(hotels) < 15:
        raise RuntimeError(f'Найдено только {len(hotels)} отелей: проверить bbox, не сочинять данные')
    (root / 'hotels.json').write_text(json.dumps(hotels, ensure_ascii=False, indent=2))
    print(f'OSM hotels: {len(hotels)}; snapshot elements: {len(snapshot["elements"])}', flush=True)

    graph_path = root / 'walk.graphml'
    if not graph_path.exists() or args.refresh:
        import osmnx as ox
        ox.settings.cache_folder = str(root / 'osm_cache')
        ox.settings.use_cache = True
        ox.settings.requests_timeout = 120
        ox.settings.overpass_url = settings.overpass_url.rsplit('/interpreter', 1)[0]
        # Теги нужны для последующей проверки доступа/барьеров.
        ox.settings.useful_tags_way = list(set(ox.settings.useful_tags_way + ['foot','access','barrier','oneway:foot','foot:conditional','access:conditional']))
        ox.settings.useful_tags_node = list(set(ox.settings.useful_tags_node + ['barrier','access','foot']))
        s, w, n, e = region['bbox_south_west_north_east']
        graph = ox.graph_from_bbox((w, s, e, n), network_type='walk', simplify=False, retain_all=True)
        ox.save_graphml(graph, graph_path)
        metadata = {'collected_at': datetime.now(timezone.utc).isoformat(),
                    'network_type': 'walk', 'simplify': False, 'osmnx_version': ox.__version__,
                    'nodes': len(graph), 'edges': graph.number_of_edges(),
                    'sha256': hashlib.sha256(graph_path.read_bytes()).hexdigest(),
                    'bbox_south_west_north_east': [s,w,n,e],
                    'endpoint': settings.overpass_url, 'license': 'ODbL-1.0'}
        (root / 'graph_metadata.json').write_text(json.dumps(metadata, indent=2))
        print(json.dumps(metadata), flush=True)


if __name__ == '__main__':
    main()
