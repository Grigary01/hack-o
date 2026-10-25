"""Синтетические контрактные тесты, НЕ разметка воздуха или акустики Адлера."""
from datetime import datetime, timedelta, timezone
from dataclasses import replace
import json
from types import SimpleNamespace
import httpx
import pytest
from shapely.geometry import Polygon, Point
from app.core.config import settings
from app.environment.air_quality import OpenAQProvider, summarize_hours
from app.environment.noise import facade_receivers, prepare_scene, building_polygon, validate_traffic
from app.environment.service import save_report, latest_reports
from app.geo.geometry import PROJECT, UNPROJECT
from app.main import create_app
from fastapi.testclient import TestClient

NOW = datetime(2026,10,25,12,tzinfo=timezone.utc)
START = NOW-timedelta(days=7)
HOTEL = SimpleNamespace(id='osm:way:1',lat=43.43,lon=39.92)


def hours(count=168, value=10, start=START, coverage=100):
    return [dict(value=value, parameter={'name':'pm25','units':'µg/m³'},
                 period={'datetimeFrom':{'utc':(start+timedelta(hours=i)).isoformat()},
                         'datetimeTo':{'utc':(start+timedelta(hours=i+1)).isoformat()}},
                 coverage={'percentCoverage':coverage}) for i in range(count)]


def test_no_key_does_not_claim_no_stations():
    report=OpenAQProvider().collect(HOTEL, NOW)
    assert report['status']=='not_configured'
    assert report['selected'] is None


def test_hour_coverage_duplicates_future_bad_units_and_conflicts():
    rows=hours()
    rows += hours(1) # Дубликат не увеличивает полноту.
    rows += hours(1, start=NOW) # Будущий интервал исключён.
    rows += hours(1, value=11) # Конфликт первого часа исключает его целиком.
    rows += hours(1, value=10) # Даже ещё один дубликат не «лечит» конфликт.
    result=summarize_hours(rows,START,NOW,'µg/m³')
    assert result['valid_hours']==167 and result['mean_pm25']==10
    assert result['rejected_rows']==1
    assert result['eligible']
    assert not summarize_hours(hours(),START,NOW,'ppm')['eligible']


def test_incomplete_stale_negative_or_missing_coverage_not_eligible():
    assert not summarize_hours(hours(100),START,NOW,'µg/m³')['eligible']
    assert not summarize_hours(hours(value=-1),START,NOW,'µg/m³')['eligible']
    assert not summarize_hours(hours(coverage=50),START,NOW,'µg/m³')['eligible']
    rows=hours()
    for row in rows: row['coverage']={}
    assert summarize_hours(rows,START,NOW,'µg/m³')['mean_pm25'] is None


def test_nearest_suitable_station_not_just_first_or_latest():
    def response(request):
        assert request.headers['X-API-Key']=='secret-test'
        if request.url.path.endswith('/locations'):
            assert request.url.params['coordinates']=='43.43,39.92'
            rows=[dict(id=i,name=f'station{i}',isMobile=False,
                       coordinates={'latitude':43.43+i*.001,'longitude':39.92}) for i in (2,1)]
        elif request.url.path.endswith('/sensors'):
            ident=int(request.url.path.split('/')[-2])
            rows=[dict(id=ident,parameter={'name':'pm25','units':'µg/m³'})]
        else:
            ident=int(request.url.path.split('/')[-2])
            rows=hours(10 if ident==1 else 168)
        return httpx.Response(200,json={'results':rows})
    report=OpenAQProvider('secret-test',httpx.MockTransport(response)).collect(HOTEL,NOW)
    assert report['status']=='available'
    assert report['selected']['station_id']==2
    assert report['selected']['sensor_id']==2
    assert 'secret-test' not in json.dumps(report)


@pytest.mark.parametrize('code,status',[(200,'no_stations'),(401,'provider_error'),(429,'provider_error')])
def test_no_stations_is_different_from_provider_failure(code,status):
    transport=httpx.MockTransport(lambda _:httpx.Response(code,json={'results':[]}))
    report=OpenAQProvider('secret',transport).collect(HOTEL,NOW)
    assert report['status']==status and report['selected'] is None


def test_pagination_limit_is_error_not_empty_success():
    def handler(request):
        return httpx.Response(200,json={'results':[{}]*1000,'meta':{'found':'>1000'}})
    report=OpenAQProvider('x',httpx.MockTransport(handler)).collect(HOTEL,NOW)
    assert report['reason']=='pagination_limit_reached'


def synthetic_snapshot():
    x,y=PROJECT(HOTEL.lon,HOTEL.lat)
    def geom(points):
        return [dict(zip(('lon','lat'),UNPROJECT(x+a,y+b))) for a,b in points]
    return {'metadata':{'source':'SYNTHETIC TEST, not real Adler data'},'elements':[
        {'type':'way','id':1,'tags':{'building':'hotel','height':'12'},
         'geometry':geom([(-10,-10),(10,-10),(10,10),(-10,10),(-10,-10)])},
        {'type':'way','id':2,'tags':{'highway':'residential'},
         'geometry':geom([(-100,-30),(100,-30)])}]}


def test_facade_points_outside_at_requested_heights_and_azimuths():
    polygon=Polygon([(0,0),(20,0),(20,20),(0,20)])
    points=facade_receivers(polygon,[4,7])
    assert len(points)==16
    assert {p['azimuth'] for p in points}=={0,90,180,270}
    assert {p['z'] for p in points}=={4,7}
    assert all(polygon.distance(Point(p['x'],p['y']))==2 for p in points)
    with pytest.raises(ValueError): facade_receivers(polygon,[float('nan')])


def test_noise_needs_traffic_and_height_but_explicit_scenario_can_run():
    snapshot=synthetic_snapshot()
    snapshot['elements'][0]['tags'].pop('height')
    report,scene=prepare_scene(HOTEL,snapshot)
    assert scene is None and report['status']=='needs_data'
    assert 'missing_building_heights' in report['gaps']
    report,scene=prepare_scene(HOTEL,snapshot,scenario=True)
    assert scene and report['status']=='ready_scenario'
    assert report['assumed_height_count']==1
    assert scene['roads'][0]['traffic']['LV_D']==100


def test_missing_building_does_not_guess_nearest_hotel():
    hotel=SimpleNamespace(id='osm:node:999',lat=43.431,lon=39.92)
    report,scene=prepare_scene(hotel,synthetic_snapshot(),scenario=True)
    assert scene is None and report['gaps']==['missing_or_ambiguous_hotel_building']


def test_receiver_above_roof_and_invalid_traffic_rejected():
    report,scene=prepare_scene(HOTEL,synthetic_snapshot(),heights=[15],scenario=True)
    assert scene is None and report['gaps']==['receiver_at_or_above_roof']
    with pytest.raises(ValueError): validate_traffic({'source_ref':'measured'})


def test_history_freshness_api_and_ranking_are_separate(repo,client):
    hotel=repo.hotels()[0]
    before=len(repo.observations(hotel.id))
    report=OpenAQProvider().collect(hotel, NOW-timedelta(days=2))
    save_report(repo,report)
    assert latest_reports(repo,hotel.id,NOW)['air_quality']['cache_stale']
    assert len(repo.observations(hotel.id))==before
    assert client.get('/api/hotels/nonexistent/environment').status_code==404


def test_refresh_api_without_key_persists_explicit_status(engine):
    with TestClient(create_app(engine=engine,config=replace(settings,openaq_api_key=''))) as client:
        hid=client.get('/api/hotels').json()[0]['id']
        result=client.post(f'/api/hotels/{hid}/environment/air-quality/refresh')
        assert result.status_code==200 and result.json()['status']=='not_configured'
        assert client.get(f'/api/hotels/{hid}/environment').json()['air_quality']['report_id']
