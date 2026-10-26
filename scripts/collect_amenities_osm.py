"""Online-команда: заведения с часами работы вокруг отелей (аптеки, магазины, кафе, АЗС).

Сервер это не вызывает; результат — data/environment/osm_amenities.json.
"""
import argparse
import json
from pathlib import Path
from app.core.config import settings
from app.geo.osm_provider import fetch_snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('data/environment/osm_amenities.json'))
    args = parser.parse_args()
    region = json.loads((settings.demo_dir / 'region.json').read_text())
    s, w, n, e = region['hotel_bbox_south_west_north_east']
    bbox = f'({s - .01},{w - .013},{n + .01},{e + .013})'
    filters = ['["amenity"~"^(pharmacy|cafe|restaurant|fast_food|fuel|bar|pub|nightclub|atm|hospital|clinic)$"]',
               '["shop"~"^(convenience|supermarket|kiosk|alcohol|bakery)$"]',
               '["healthcare"="pharmacy"]']
    query = '[out:json][timeout:90];(' + ''.join(f'nwr{f}{bbox};' for f in filters) + ');out center tags;'
    snapshot = fetch_snapshot(settings.overpass_url, query, args.output, args.refresh)
    with_hours = sum('opening_hours' in x.get('tags', {}) for x in snapshot['elements'])
    print(json.dumps({'elements': len(snapshot['elements']), 'with_opening_hours': with_hours}, ensure_ascii=False))


if __name__ == '__main__':
    main()
