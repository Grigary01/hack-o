"""Online-команда: ВПП и аэродром Сочи (AER) из OSM для оценки авиашума.

Сервер это не вызывает; результат кладётся в data/environment/osm_aeroways.json.
"""
import argparse
import json
from pathlib import Path
from app.core.config import settings
from app.geo.osm_provider import fetch_snapshot

# Аэродром Сочи с запасом: ВПП 06/24 и 02/20 целиком внутри.
AIRPORT_BBOX = (43.42, 39.92, 43.48, 39.99)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('data/environment/osm_aeroways.json'))
    args = parser.parse_args()
    s, w, n, e = AIRPORT_BBOX
    query = (f'[out:json][timeout:60];(way["aeroway"="runway"]({s},{w},{n},{e});'
             f'nwr["aeroway"="aerodrome"]["iata"="AER"]({s},{w},{n},{e}););out body geom;')
    snapshot = fetch_snapshot(settings.overpass_url, query, args.output, args.refresh)
    runways = [x['tags'].get('ref') for x in snapshot['elements'] if x.get('tags', {}).get('aeroway') == 'runway']
    print(json.dumps({'elements': len(snapshot['elements']), 'runways': runways,
                      'collected_at': snapshot['metadata']['collected_at']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
