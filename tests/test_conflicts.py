from datetime import timedelta
from app.features.service import resolve_feature
from app.storage.repository import now_utc


def test_conflict_preserves_both_versions_and_blocks_value(repo,observation):
    hotel=repo.hotels()[0]
    a=observation(hotel.id,'sea_view',True,room='301',source='hotelier_simulated')
    b=observation(hotel.id,'sea_view',False,room='301',source='hotelier_simulated')
    repo.save_observation(a);repo.save_observation(b);repo.save_observation(a)
    assert len(repo.observations(hotel.id,'sea_view'))==2
    assert len(repo.conflicts(hotel.id))==1
    state=resolve_feature([a,b],a.subject_id,'sea_view',True)
    assert state.value is None and state.status=='conflicted'


def test_expired_disjoint_period_and_room_do_not_conflict(repo,observation):
    h=repo.hotels()[0]
    old=observation(h.id,'sea_view',False,room='301',offset=-30)
    fresh=observation(h.id,'sea_view',True,room='301')
    other=observation(h.id,'sea_view',False,room='302')
    for o in [old,fresh,other]:repo.save_observation(o)
    assert not repo.conflicts(h.id)
    assert resolve_feature([old],old.subject_id,'sea_view').status=='stale'
    assert resolve_feature([old,fresh],old.subject_id,'sea_view').value is True


def test_simulated_and_future_facts_do_not_leak(observation):
    sim=observation('h','sea_view',True,room='301',source='hotelier_simulated')
    assert resolve_feature([sim],sim.subject_id,'sea_view').value is None
    assert resolve_feature([sim],sim.subject_id,'sea_view',True).value is True
    future=observation('h','sea_view',True,room='302',offset=3)
    assert resolve_feature([future],future.subject_id,'sea_view').value is None
