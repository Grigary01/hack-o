"""Отдельная выгрузка контуров зданий; не изменяет исходный demo snapshot.

Отступ 1 км вокруг hotel bbox нужен для препятствий и источников около границ.
OSM может быть неполным: наличие контура не означает наличие высоты.
"""
import argparse
import json
from pathlib import Path
from app.core.config import settings
from app.geo.osm_provider import fetch_snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('data/environment/osm_buildings.json'))
    args = parser.parse_args()
    region = json.loads((settings.demo_dir / 'region.json').read_text())
    s, w, n, e = region['hotel_bbox_south_west_north_east']
    # На широте Адлера 0.013° longitude и 0.01° latitude чуть больше километра.
    bbox = f'({s-.01},{w-.013},{n+.01},{e+.013})'
    filters = ['["building"]', '["highway"]', '["railway"="rail"]',
               '["amenity"~"^(bar|pub|nightclub)$"]', '["barrier"]']
    query = '[out:json][timeout:90];(' + ''.join(f'nwr{f}{bbox};' for f in filters) + ');out body geom;'
    snapshot = fetch_snapshot(settings.overpass_url, query, args.output, args.refresh)
    print(json.dumps({'elements': len(snapshot['elements']), 'metadata': snapshot['metadata']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
