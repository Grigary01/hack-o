"""Повторный seed не удаляет ответы отельера и не дублирует наблюдения."""
import json
import argparse
from sqlalchemy.orm import Session
from app.core.config import settings
from app.features.registry import get_registry
from app.schemas.hotel import Hotel, Observation
from app.storage.db import create_db
from app.storage.repository import Repository


def seed(engine, directory=settings.demo_dir, environment=False):
    hotels = [Hotel.model_validate(x) for x in json.loads((directory/'hotels.json').read_text())]
    observations = [Observation.model_validate(x) for x in json.loads((directory/'features.json').read_text())]
    with Session(engine) as session, session.begin():
        repo = Repository(session)
        repo.save_definitions(get_registry())
        for hotel in hotels:
            repo.save_hotel(hotel)
        for observation in observations:
            repo.save_observation(observation)
        if environment:
            from app.environment.service import save_report
            for name in ('preparation_reports.json','adler_scenario.json','air_quality_status.json'):
                source = directory.parent/'environment'/name
                if source.is_file():
                    for report in json.loads(source.read_text()):
                        save_report(repo, report)
    return {'hotels':len(hotels), 'observations':len(observations)}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--environment',action='store_true',help='Загрузить отчёты среды, включая явно помеченный учебный сценарий')
    print(seed(create_db(settings.database_url),environment=parser.parse_args().environment))
