import pytest
from pydantic import ValidationError
from app.schemas.query import SoftPreference, UtilityCurve, ParsedHotelQuery, HardConstraint
from app.ml.multicriteria import aggregate, curve_match
from app.ml.ranking import rank_hotels


def preference(key,desired='high',weight=1,scope='hotel',utility=None):
    return SoftPreference(feature_key=key,desired=desired,importance=weight,
                          weight_source='explicit',scope=scope,utility=utility)


def test_continuous_lower_higher_and_target_band():
    lower=UtilityCurve(kind='lower',ideal_max=200,tolerance=400)
    assert [curve_match(x,lower) for x in (0,200,400,600,900)]==[1,1,.5,0,0]
    higher=UtilityCurve(kind='higher',ideal_min=300,tolerance=200)
    assert [curve_match(x,higher) for x in (100,200,300,600)]==[0,.5,1,1]
    band=UtilityCurve(kind='target_range',ideal_min=300,ideal_max=500,tolerance=200)
    assert [curve_match(x,band) for x in (100,200,300,400,500,600,700)]==[0,.5,1,1,1,.5,0]


def test_bad_curve_or_curve_on_boolean_is_rejected():
    with pytest.raises(ValidationError): UtilityCurve(kind='target_range',ideal_min=500,ideal_max=300,tolerance=100)
    with pytest.raises(ValidationError): UtilityCurve(kind='lower',ideal_max=200,tolerance=0)
    with pytest.raises(ValidationError):
        preference('sea_view',True,scope='room',utility=UtilityCurve(kind='lower',ideal_max=1,tolerance=1))


def test_correlated_duplicate_signal_does_not_double_group_weight():
    quiet=preference('quietness_proxy')
    distance=preference('nightlife_distance_m','far')
    beach=preference('walking_distance_to_beach_m','near')
    first=aggregate([quiet,beach],{'quietness_proxy':.2,'walking_distance_to_beach_m':1})
    second=aggregate([quiet,distance,beach],{'quietness_proxy':.2,'nightlife_distance_m':.2,'walking_distance_to_beach_m':1})
    assert second['lower']==pytest.approx(first['lower'])
    assert len(second['groups'])==2


def test_balanced_variant_beats_equal_mean_extreme_tradeoff():
    prefs=[preference('quietness_proxy'),preference('walking_distance_to_beach_m','near')]
    extreme=aggregate(prefs,{'quietness_proxy':0,'walking_distance_to_beach_m':1})
    balanced=aggregate(prefs,{'quietness_proxy':.5,'walking_distance_to_beach_m':.5})
    assert balanced['lower']>extreme['lower']


def test_unknown_is_interval_not_fake_value_and_monotonic():
    prefs=[preference('quietness_proxy'),preference('sea_view',True,scope='room')]
    uncertain=aggregate(prefs,{'quietness_proxy':1,'sea_view':None})
    assert uncertain['coverage']==.5 and uncertain['lower']<uncertain['upper']
    for value in (0,.3,1):
        known=aggregate(prefs,{'quietness_proxy':1,'sea_view':value})
        assert uncertain['lower']<=known['lower']<=uncertain['upper']
        assert known['lower']==known['upper']
    assert aggregate([], {})['score'] is None


def test_near_nightlife_is_not_silence_group():
    result=aggregate([preference('nightlife_distance_m','near'),preference('quietness_proxy')],
                     {'nightlife_distance_m':1,'quietness_proxy':0})
    assert len(result['groups'])==2


def test_v2_cannot_compensate_hard_violation(repo,observation):
    hotel=repo.hotels()[0]
    facts=[observation(hotel.id,'walking_distance_to_beach_m',1000),observation(hotel.id,'quietness_proxy','high')]
    query=ParsedHotelQuery(hard_constraints=[HardConstraint(feature_key='walking_distance_to_beach_m',operator='<=',value=500,unit='m')],
                           soft_preferences=[preference('quietness_proxy')])
    result=rank_hotels(query,[(hotel,facts)],ranking_method='balanced_v2')
    assert result['excluded'][0].eligible is False


def test_api_selectable_versions_and_curve(client):
    query=ParsedHotelQuery(soft_preferences=[preference('walking_distance_to_beach_m','near',utility=UtilityCurve(kind='lower',ideal_max=200,tolerance=400))])
    for method in ('weighted_v1','balanced_v2'):
        response=client.post('/api/search',json={'parsed':query.model_dump(mode='json'),'ranking_method':method})
        assert response.status_code==200
        body=response.json()
        assert body['ranking_method']==method
        result=body['matched'][0]
        assert result['ranking_method']==method
        if method=='balanced_v2':
            assert result['group_scores'] and result['ranking_interval']
