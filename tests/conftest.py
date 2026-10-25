import socket
import json
import uuid
from datetime import timedelta, datetime
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.storage.db import create_db
from app.storage.repository import Repository, now_utc
from app.schemas.hotel import Observation, Evidence, Source, Hotel
from scripts.seed_demo import seed
from app.main import create_app
from app.ml.query_parser import FixtureQueryParser
from app.core.config import settings

TEST_NOW=datetime.fromisoformat(json.loads((settings.demo_dir/'graph_metadata.json').read_text())['collected_at'])+timedelta(hours=1)


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    def denied(*args,**kwargs):
        raise AssertionError('Unit tests must not access the network')
    monkeypatch.setattr(socket.socket,'connect',denied)
    # Тесты старого snapshot воспроизводимы и после TTL; production использует настоящие часы.
    for module in ('app.storage.repository','app.features.service','app.hotelier.dialogue','app.agent.feature_agent'):
        monkeypatch.setattr(module+'.now_utc',lambda:TEST_NOW)


@pytest.fixture
def engine():
    db=create_db('sqlite://')
    seed(db)
    yield db
    db.dispose()


@pytest.fixture
def repo(engine):
    with Session(engine) as session,session.begin():
        yield Repository(session)


@pytest.fixture
def client(engine):
    with TestClient(create_app(engine=engine,parser=FixtureQueryParser())) as c:
        yield c


@pytest.fixture
def observation():
    def make(hotel_id,key,value,room=None,offset=0,source='openstreetmap'):
        from app.features.registry import get_registry
        now=TEST_NOW+timedelta(days=offset)
        return Observation(id=uuid.uuid4().hex,hotel_id=hotel_id,
            subject_type='room' if room else 'hotel',subject_id=f'{hotel_id}:room:{room}' if room else hotel_id,
            feature_key=key,value=value,unit=get_registry().get(key).unit,
            observed_at=now-timedelta(seconds=2),collected_at=now,expires_at=now+timedelta(days=10),
            status='estimated' if value is not None else 'unknown',confidence_level='low',
            confidence_method='Synthetic test only',evidence=Evidence(source=Source(type=source,name='Test fixture',ref='test'),method='test'))
    return make
