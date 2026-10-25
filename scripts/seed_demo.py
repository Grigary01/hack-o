"""Повторный seed не удаляет ответы отельера и не дублирует наблюдения."""
import json
from sqlalchemy.orm import Session
from app.core.config import settings
from app.features.registry import get_registry
from app.schemas.hotel import Hotel, Observation
from app.storage.db import create_db
from app.storage.repository import Repository


def seed(engine, directory=settings.demo_dir):
    hotels = [Hotel.model_validate(x) for x in json.loads((directory/'hotels.json').read_text())]
    observations = [Observation.model_validate(x) for x in json.loads((directory/'features.json').read_text())]
    with Session(engine) as session, session.begin():
        repo = Repository(session)
        repo.save_definitions(get_registry())
        for hotel in hotels:
            repo.save_hotel(hotel)
        for observation in observations:
            repo.save_observation(observation)
    return {'hotels':len(hotels), 'observations':len(observations)}


if __name__=='__main__':
    print(seed(create_db(settings.database_url)))
