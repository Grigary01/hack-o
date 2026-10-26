import subprocess
import sys
from datetime import timedelta
from types import SimpleNamespace
from app.core.config import ROOT
from app.environment.noise import building_polygon
from app.features.service import resolve_feature
from app.geo.change_detection import affected_hotels, diff_buildings, simulated_building
from app.schemas.hotel import Observation

LAT, LON = 43.4253, 39.91481


def test_diff_finds_added_removed_and_modified():
    a = simulated_building(LAT, LON, 3, osm_id_value=1)
    b = simulated_building(LAT + .001, LON, 5, osm_id_value=2)
    taller = simulated_building(LAT, LON, 9, osm_id_value=1)
    new = simulated_building(LAT, LON + .001, 12, osm_id_value=3)
    changes = {c['osm_id']: c for c in diff_buildings([a, b], [taller, new])}
    assert changes['osm:way:1']['change'] == 'modified' and changes['osm:way:1']['previous_height_m'] == 9.
    assert changes['osm:way:2']['change'] == 'removed' and changes['osm:way:3']['change'] == 'added'
    assert changes['osm:way:3']['simulated']


def test_affected_by_radius_or_by_blocking_role():
    near = {'osm_id': 'osm:way:1', 'change': 'added', 'polygon': building_polygon(simulated_building(LAT, LON + .0005, 3))}
    far = {'osm_id': 'osm:way:9', 'change': 'removed', 'polygon': building_polygon(simulated_building(LAT + .05, LON, 3))}
    hotel = SimpleNamespace(id='h', lat=LAT, lon=LON)
    assert [c['osm_id'] for c in affected_hotels([near, far], [hotel], {})['h']] == ['osm:way:1']
    blocking = {'h': {'base': {'best_sea': {'blocking_buildings': ['osm:way:9']}}}}
    hits = affected_hotels([far], [hotel], blocking)['h']
    assert hits[0]['was_blocking'] and hits[0]['distance_m'] > 1500


def test_newer_snapshot_of_same_model_supersedes_without_conflict(repo, observation):
    hotel = repo.hotels()[0]
    old = observation(hotel.id, 'sea_view_potential', 'wide', source='openstreetmap')
    new = observation(hotel.id, 'sea_view_potential', 'partial', offset=1, source='openstreetmap')
    repo.save_observation(old)
    repo.save_observation(new)
    pair = {old.id, new.id}
    assert not [c for c in repo.conflicts(hotel.id) if {c['left_id'], c['right_id']} == pair]
    state = resolve_feature([old, new], hotel.id, 'sea_view_potential', now=new.observed_at + timedelta(hours=1))
    assert state.value == 'partial'
    # Разные источники по-прежнему конфликтуют.
    other = observation(hotel.id, 'sea_view_potential', 'none', offset=1, source='hotelier')
    state = resolve_feature([new, other], hotel.id, 'sea_view_potential', now=new.observed_at + timedelta(hours=1))
    assert state.status == 'conflicted'


def test_simulated_refresh_cannot_be_applied():
    result = subprocess.run([sys.executable, '-m', 'scripts.refresh_geo', '--simulate-building', f'{LAT},{LON},12',
                             '--apply'], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0 and 'запрещён' in result.stderr
