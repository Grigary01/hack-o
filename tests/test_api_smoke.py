import json
from app.core.config import settings
from app.ml.query_parser import FixtureQueryParser


def test_offline_api_pipeline_and_errors(client):
    health=client.get('/api/health')
    assert health.status_code==200 and health.json()['hotels']==25
    assert client.get('/health').json()=={'status':'ok','hotels':25}
    text=FixtureQueryParser().examples[0]['text']
    parsed=client.post('/api/parse-query',json={'text':text})
    assert parsed.status_code==200
    response=client.post('/api/search',json={'text':text})
    assert response.status_code==200
    body=response.json()
    assert sum(len(body[k]) for k in ('matched','excluded','needs_verification'))==25
    assert len(body['matched'])>0 and len(body['needs_verification'])>0
    first=body['matched'][0]
    route=next(c for c in first['criteria'] if c['feature_key']=='walking_distance_to_beach_m')
    assert route['actual']<=500
    assert route['evidence'][0]['evidence']['method']=='pedestrian_graph'
    assert route['evidence'][0]['confidence'] is None
    assert client.get('/api/hotels/no-such-id').status_code==404
    assert client.post('/api/search',json={}).status_code==422
    assert client.post('/api/search',json={'text':text,'weights':{'sea_view':2}}).status_code==422
    assert client.post('/api/search',json={'text':text,'weights':{'not_a_feature':.5}}).status_code==422
    assert client.post('/api/search',json={'text':'Хочу невозможную характеристику'}).json()['status']=='needs_clarification'


def test_hotelier_workflow_changes_only_demo_search_and_detects_conflict(client):
    hotel=client.get('/api/hotels').json()[0]
    q=client.post('/api/hotelier/questions',json={'hotel_id':hotel['id'],'feature_key':'sea_view'}).json()
    for value in ['В номере 301 есть вид на море.','В номере 301 нет вида на море.']:
        answer=client.post(f'/api/hotelier/questions/{q["id"]}/answer',json={'text':value})
        assert answer.status_code==200
        confirmed=client.post(f'/api/hotelier/answers/{answer.json()["id"]}/confirm',json={'accept':True})
        assert confirmed.status_code==200
        if 'есть' in value:
            real=client.post('/api/search',json={'text':'Нужен номер обязательно с видом на море'}).json()
            assert not real['matched']
            demo=client.post('/api/search',json={'text':'Нужен номер обязательно с видом на море','include_simulated':True}).json()
            assert [r['hotel']['id'] for r in demo['matched']]==[hotel['id']]
    assert len(confirmed.json()['conflicts'])==1
    body=client.post('/api/search',json={'text':'Нужен номер обязательно с видом на море','include_simulated':True}).json()
    assert not body['matched']
    evidence=client.get(f'/api/hotels/{hotel["id"]}/evidence').json()
    assert len([o for o in evidence['observations'] if o['feature_key']=='sea_view'])==2


def test_seed_is_idempotent_without_erasing_answers(client,engine):
    from scripts.seed_demo import seed
    hotel=client.get('/api/hotels').json()[0]
    q=client.post('/api/hotelier/questions',json={'hotel_id':hotel['id'],'feature_key':'sea_view'}).json()
    answer=client.post(f'/api/hotelier/questions/{q["id"]}/answer',json={'text':'В номере 301 вид на море.'}).json()
    client.post(f'/api/hotelier/answers/{answer["id"]}/confirm',json={'accept':True})
    seed(engine);seed(engine)
    rows=client.get(f'/api/hotels/{hotel["id"]}/evidence').json()['observations']
    seeded=[o for o in json.loads((settings.demo_dir/'features.json').read_text()) if o['hotel_id']==hotel['id']]
    assert len(rows)==len(seeded)+1


def test_health_reports_empty_database():
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.storage.db import create_db
    with TestClient(create_app(engine=create_db('sqlite://'),parser=FixtureQueryParser())) as c:
        response=c.get('/health')
    assert response.status_code==503 and response.json()['status']=='needs_seed'
