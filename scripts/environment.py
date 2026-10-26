"""CLI: подготовить геометрию / получить воздух / запустить внешний движок.

python -m scripts.environment prepare-noise --all
python -m scripts.environment air --hotel-id osm:way:...
python -m scripts.environment run-noise --hotel-id osm:way:... --scenario
"""
import argparse
import json
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.config import settings
from app.storage.db import create_db
from app.storage.repository import Repository
from app.environment.air_quality import OpenAQProvider
from app.environment.noise import prepare_scene, run_noisemodelling
from app.environment.service import save_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['air','prepare-noise','run-noise'])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--hotel-id')
    group.add_argument('--all', action='store_true')
    parser.add_argument('--snapshot', type=Path, default=Path('data/environment/osm_buildings.json'))
    parser.add_argument('--heights', type=float, nargs='+', default=[4.])
    parser.add_argument('--scenario', action='store_true', help='Условные трафик и пропущенные высоты, не реальные данные')
    parser.add_argument('--traffic', type=Path, help='JSON: osm_id → source_ref и транспорт по периодам')
    parser.add_argument('--nm-home', default=settings.noisemodelling_home)
    parser.add_argument('--java-home', default=settings.noise_java_home)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.all and args.action != 'prepare-noise':
        parser.error('--all разрешён только для офлайн-подготовки, чтобы не запускать десятки тяжёлых запросов')
    if args.scenario and args.traffic:
        parser.error('Укажите либо --scenario, либо реальные --traffic')
    engine = create_db(settings.database_url)
    with Session(engine) as session, session.begin():
        repo = Repository(session)
        hotels = repo.hotels() if args.all else [repo.hotel(args.hotel_id)]
        snapshot = json.loads(args.snapshot.read_text()) if args.action != 'air' else None
        traffic = json.loads(args.traffic.read_text()) if args.traffic else None
        reports = []
        for hotel in hotels:
            if args.action == 'air':
                report = OpenAQProvider(settings.openaq_api_key).collect(hotel)
            else:
                report, scene = prepare_scene(hotel, snapshot, args.heights, args.scenario, traffic)
                if args.action == 'run-noise':
                    if scene is None:
                        print(json.dumps({'hotel_id':hotel.id, 'status':report['status'], 'gaps':report['gaps']}, ensure_ascii=False))
                    else:
                        report = run_noisemodelling(report, scene, args.nm_home, args.java_home)
            save_report(repo, report)
            reports.append(report)
            print(json.dumps({'hotel_id':hotel.id, 'status':report['status'],
                              'receivers':len(report.get('receivers', [])),
                              'levels':len(report.get('levels', []))}, ensure_ascii=False))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(reports, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
