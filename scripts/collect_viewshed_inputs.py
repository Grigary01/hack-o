"""Online-подготовка входов viewshed: береговая линия OSM и рельеф Copernicus GLO-30.

Сервер и поиск это не вызывают. Результат кладётся в data/environment/ и
коммитится, чтобы демо работало без сети. Здания уже есть в osm_buildings.json.

DEM читается окнами из публичных COG на AWS (rasterio /vsicurl/), поэтому
скачиваются только нужные блоки, а не тайлы 1°×1° целиком. Нужен extra [geo].
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from app.core.config import settings
from app.geo.osm_provider import fetch_snapshot

OUT = Path('data/environment')
# Область рельефа шире области отелей: на северо-западе (~15 км) хребет Ахун,
# он может закрывать летний закат; на северо-востоке (~40 км) Главный Кавказский
# хребет (Ачишхо, Аибга, >2300 м) — его снежные вершины видны с верхних этажей.
DEM_BOUNDS = dict(south=43.30, west=39.65, north=43.80, east=40.45)
# Береговая линия: лучи к морю идут до ~10 км, плюс запас для полигона моря.
COAST_BBOX = (43.25, 39.60, 43.70, 40.15)
COG = ('https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM/'
       'Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM.tif')
DEM_ATTRIBUTION = ('Copernicus DEM GLO-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 '
                   'provided under COPERNICUS by the European Union and ESA; all rights reserved')


def collect_coastline(refresh):
    s, w, n, e = COAST_BBOX
    query = f'[out:json][timeout:90];(way["natural"="coastline"]({s},{w},{n},{e}););out body geom;'
    snapshot = fetch_snapshot(settings.overpass_url, query, OUT/'osm_coastline.json', refresh)
    return {'elements': len(snapshot['elements']), 'collected_at': snapshot['metadata']['collected_at']}


def collect_vegetation(refresh):
    """Деревья, рядки, лес и кустарник OSM в той же области, что и здания."""
    s, w, n, e = 43.414, 39.893, 43.46, 39.951
    query = ('[out:json][timeout:90];(nwr["natural"~"^(tree|tree_row|wood|scrub)$"]'
             f'({s},{w},{n},{e});nwr["landuse"="forest"]({s},{w},{n},{e}););out body geom;')
    snapshot = fetch_snapshot(settings.overpass_url, query, OUT/'osm_vegetation.json', refresh)
    return {'elements': len(snapshot['elements']), 'collected_at': snapshot['metadata']['collected_at']}


def collect_dem():
    import rasterio
    from rasterio.merge import merge
    b = DEM_BOUNDS
    tiles = sorted({(lat, lon) for lat in range(int(b['south']), int(b['north'])+1)
                    for lon in range(int(b['west']), int(b['east'])+1)})
    urls = [COG.format(lat=lat, lon=lon) for lat, lon in tiles]
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif'):
        sources = [rasterio.open('/vsicurl/' + url) for url in urls]
        try:
            # Тайлы Copernicus при одинаковой широте имеют одинаковый шаг по долготе.
            res = sources[0].res
            mosaic, transform = merge(sources, bounds=(b['west'], b['south'], b['east'], b['north']),
                                      res=res, nodata=-32767)
            nodata_tiles = [s.nodata for s in sources]
        finally:
            for s in sources:
                s.close()
    elevation = mosaic[0].astype(np.float32)
    # merge может оставить пустой крайний столбец/строку справа и снизу (округление границы);
    # их обрезка не меняет привязку (левый верхний угол тот же).
    while np.all(elevation[:, -1] <= -1000):
        elevation = elevation[:, :-1]
    while np.all(elevation[-1, :] <= -1000):
        elevation = elevation[:-1, :]
    if np.any(elevation <= -1000):
        raise ValueError('В окне DEM есть пропуски nodata: проверить тайлы, не заполнять выдумкой')
    # Дециметры в int16 (до 3276 м) — без потери значимой точности GLO-30 (~2-4 м).
    decimetres = np.round(elevation * 10).astype(np.int16)
    target = OUT/'dem_copernicus_glo30.npz'
    np.savez_compressed(target, elevation_dm=decimetres)
    metadata = {
        'product': 'Copernicus DEM GLO-30 (DSM)', 'urls': urls, 'nodata': nodata_tiles,
        'collected_at': datetime.now(timezone.utc).isoformat(),
        'crs': 'EPSG:4326',
        # Фактические границы после обрезки пустых краёв.
        'bounds': {'west': transform.c, 'north': transform.f,
                   'east': transform.c + transform.a * decimetres.shape[1],
                   'south': transform.f + transform.e * decimetres.shape[0]},
        # Аффинное преобразование rasterio: lon = c + a*col, lat = f + e*row (центр пикселя +0.5).
        'transform': [transform.a, transform.b, transform.c, transform.d, transform.e, transform.f],
        'shape': list(decimetres.shape), 'unit': 'decimetre', 'vertical_datum': 'EGM2008',
        'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'license': 'Copernicus DEM licence (free use with attribution)', 'attribution': DEM_ATTRIBUTION,
        'limits': ['dsm_includes_vegetation_and_buildings_partially', 'horizontal_resolution_~30m',
                   'acquisition_2011_2015_not_current'],
    }
    (OUT/'dem_copernicus_glo30.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    return {k: metadata[k] for k in ('shape', 'sha256')} | {
        'min_m': float(elevation.min()), 'max_m': float(elevation.max())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true', help='Перезапросить Overpass вместо кеша')
    parser.add_argument('--skip-dem', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'coastline': collect_coastline(args.refresh), 'vegetation': collect_vegetation(args.refresh)}
    if not args.skip_dem:
        report['dem'] = collect_dem()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
