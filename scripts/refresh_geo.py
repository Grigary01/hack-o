"""Актуализация вида из окон по новому снимку зданий OSM.

    python -m scripts.refresh_geo --refresh                 # свежая выгрузка Overpass, отчёт без записи
    python -m scripts.refresh_geo --buildings new.json --apply
    python -m scripts.refresh_geo --simulate-building 43.42515,39.91455,12   # «построили дом» (демо)

Отчёт: runtime/refresh_report.json — изменения зданий, затронутые отели и
значения «было → стало». --apply заменяет data/environment/osm_buildings.json
и пересчитывает все расчёты вида (иначе validate_data не воспроизведёт их);
старые значения в базе не удаляются: новый снимок той же модели их заменяет
(app/features/service.py:supersedes). С симуляцией --apply запрещён.
"""
import argparse
import json
from pathlib import Path
from app.core.config import ROOT, settings
from app.geo.change_detection import diff_buildings, affected_hotels, simulated_building
from app.geo.service import GeoService, VIEWSHED_KEYS
from app.geo.viewshed import ViewshedScene
from app.schemas.hotel import Hotel


def load_new_snapshot(args, current):
    if args.simulate_building:
        lat, lon, levels = (float(v) for v in args.simulate_building.split(','))
        return {'metadata': current['metadata'] | {'note': 'SIMULATED building added for demo'},
                'elements': current['elements'] + [simulated_building(lat, lon, int(levels))]}
    if args.refresh:
        from scripts.collect_environment_osm import main as collect
        target = ROOT / 'runtime/osm_buildings.new.json'
        target.parent.mkdir(exist_ok=True)
        import sys
        sys.argv = ['collect_environment_osm', '--refresh', '--output', str(target)]
        collect()
        return json.loads(target.read_text())
    return json.loads(Path(args.buildings).read_text())


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--buildings', help='путь к новому снимку зданий (формат osm_buildings.json)')
    source.add_argument('--refresh', action='store_true', help='выгрузить свежие здания из Overpass')
    source.add_argument('--simulate-building', help='lat,lon,этажей — добавить синтетический дом (демо)')
    parser.add_argument('--apply', action='store_true', help='записать новый снимок и пересчитанные значения')
    parser.add_argument('--report', type=Path, default=ROOT / 'runtime/refresh_report.json')
    args = parser.parse_args()
    if args.apply and args.simulate_building:
        parser.error('--apply с симуляцией запрещён: синтетический дом не должен попасть в демо-данные')

    env = settings.environment_dir
    current = json.loads((env / 'osm_buildings.json').read_text())
    new = load_new_snapshot(args, current)
    hotels = [Hotel.model_validate(x) for x in json.loads((settings.demo_dir / 'hotels.json').read_text())]
    features = json.loads((settings.demo_dir / 'features.json').read_text())
    old = {(f['hotel_id'], f['feature_key']): f for f in features if f['feature_key'] in VIEWSHED_KEYS}
    details = {h: f['evidence']['details'] for (h, k), f in old.items() if k == 'sea_view_potential'}

    changes = diff_buildings(current['elements'], new['elements'])
    affected = affected_hotels(changes, hotels, details)
    geo = GeoService()
    geo.viewshed_scene = ViewshedScene.load(env, geo.region['hotel_bbox_south_west_north_east'], buildings_raw=new)
    by_id = {h.id: h for h in hotels}
    recompute = hotels if args.apply else [by_id[h] for h in affected]
    fresh = {(h.id, key): geo.compute(h, key) for h in recompute for key in VIEWSHED_KEYS}

    report = {'simulated': bool(args.simulate_building), 'building_changes': len(changes),
              'changes': [{k: v for k, v in c.items() if k != 'polygon'} for c in changes][:200],
              'affected_hotels': []}
    for hotel_id, hits in affected.items():
        diffs = []
        for key in VIEWSHED_KEYS:
            before, after = old.get((hotel_id, key)), fresh[(hotel_id, key)]
            if before is None or before['value'] != after.value:
                diffs.append({'feature_key': key, 'before': before and before['value'], 'after': after.value,
                              'explanation_after': after.evidence.details.get('explanation')})
        report['affected_hotels'].append({'hotel_id': hotel_id, 'name': by_id[hotel_id].name,
                                          'nearby_changes': hits[:10], 'value_changes': diffs})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    if args.apply:
        (env / 'osm_buildings.json').write_text(json.dumps(new, ensure_ascii=False))
        kept = [f for f in features if f['feature_key'] not in VIEWSHED_KEYS]
        (settings.demo_dir / 'features.json').write_text(json.dumps(
            kept + [o.model_dump(mode='json') for o in fresh.values()], ensure_ascii=False, indent=2))
    print(json.dumps({'building_changes': len(changes), 'affected_hotels': len(affected),
                      'value_changes': {r['name']: r['value_changes'] for r in report['affected_hotels']
                                        if r['value_changes']},
                      'applied': args.apply, 'report': str(args.report)}, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
