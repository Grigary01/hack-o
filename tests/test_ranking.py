from app.schemas.query import ParsedHotelQuery, HardConstraint, SoftPreference
from app.ml.ranking import rank_hotels


def test_hard_filters_unknown_and_violation(repo,observation):
    hotels=repo.hotels()[:3]
    rows=[(h,[observation(h.id,'walking_distance_to_beach_m',v)]) for h,v in zip(hotels,[100,700,None])]
    query=ParsedHotelQuery(hard_constraints=[HardConstraint(feature_key='walking_distance_to_beach_m',operator='<=',value=500,unit='m')])
    result=rank_hotels(query,rows)
    assert [r.hotel.id for r in result['matched']]==[hotels[0].id]
    assert [r.hotel.id for r in result['excluded']]==[hotels[1].id]
    assert [r.hotel.id for r in result['needs_verification']]==[hotels[2].id]


def test_weight_changes_order_and_zero_distance_is_valid(repo,observation):
    a,b=repo.hotels()[:2]
    rows=[(a,[observation(a.id,'walking_distance_to_beach_m',0),observation(a.id,'quietness_proxy','low')]),
          (b,[observation(b.id,'walking_distance_to_beach_m',1000),observation(b.id,'quietness_proxy','high')])]
    def query(w1,w2):
        return ParsedHotelQuery(soft_preferences=[SoftPreference(feature_key='walking_distance_to_beach_m',desired='near',importance=w1,weight_source='explicit'),
             SoftPreference(feature_key='quietness_proxy',desired='high',importance=w2,weight_source='explicit')])
    assert rank_hotels(query(1,.1),rows)['matched'][0].hotel.id==a.id
    assert rank_hotels(query(.1,1),rows)['matched'][0].hotel.id==b.id
    assert all(r.score is None for r in rank_hotels(query(0,0),rows)['matched'])


def test_missing_soft_data_is_not_perfect_rank(repo,observation):
    h=repo.hotels()[0]
    q=ParsedHotelQuery(soft_preferences=[SoftPreference(feature_key='sea_view',desired=True,scope='room')])
    result=rank_hotels(q,[(h,[])])['matched'][0]
    assert result.score is None and result.coverage==0 and result.ranking_score==0


def test_room_constraints_must_match_one_room(repo,observation):
    h=repo.hotels()[0]
    facts=[observation(h.id,'sea_view',True,room='301'),observation(h.id,'soundproofing',False,room='301'),
           observation(h.id,'sea_view',False,room='302'),observation(h.id,'soundproofing',True,room='302')]
    q=ParsedHotelQuery(hard_constraints=[HardConstraint(feature_key=k,operator='=',value=True,scope='room') for k in ['sea_view','soundproofing']])
    result=rank_hotels(q,[(h,facts)])
    assert not result['matched'] and len(result['needs_verification'])==1
