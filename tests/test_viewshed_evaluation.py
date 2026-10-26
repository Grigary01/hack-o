import json
from app.core.config import ROOT
from scripts.evaluate_viewshed import evaluate


def feature(hotel_id, key, value, details=None):
    return {'hotel_id': hotel_id, 'feature_key': key, 'value': value, 'confidence_level': 'low',
            'evidence': {'details': details or {'levels': 3, 'levels_source': 'osm_building_levels'}}}


def gold_hotel(hotel_id, label, floors=(), levels=None):
    return {'hotel_id': hotel_id, 'name': hotel_id, 'identity': {'status': 'matched'},
            'labels': {'sea_view': label}, 'floor_evidence': list(floors), 'levels_evidence': levels,
            'evidence': [{'source_type': 'guest_review', 'supports': 'sea_view=yes'}]}


def test_outcomes_floors_and_level_conflicts():
    features = [feature('a', 'sea_view_potential', 'wide'), feature('a', 'sea_view_min_floor', 5),
                feature('b', 'sea_view_potential', 'none'), feature('b', 'sea_view_min_floor', None),
                feature('c', 'sea_view_potential', 'partial'), feature('c', 'sea_view_min_floor', 2)]
    gold = {'hotels': [
        gold_hotel('a', 'yes', floors=[{'floor': 3, 'sea_view': True}],
                   levels={'min_levels': 6, 'url': 'x'}),
        gold_hotel('b', 'yes'),
        gold_hotel('c', 'no_claim'),
    ]}
    report = evaluate(gold, features)
    outcomes = {r['hotel_id']: r['outcome'] for r in report['rows']}
    assert outcomes == {'a': 'agree', 'b': 'disagree', 'c': 'unconfirmed_positive'}
    assert report['recall_on_confirmed_sea_view'] == 0.5 and report['precision'] is None
    # Гость видел море с 3-го, а модель говорит «с 5-го» — несогласованно.
    assert report['floor_checks'] == {'total': 1, 'consistent': 0}
    assert report['source_conflicts'][0]['evidence_min_levels'] == 6


def test_real_gold_file_is_well_formed():
    gold = json.loads((ROOT/'data/evaluation/view_gold.json').read_text())
    for hotel in gold['hotels']:
        assert hotel['hotel_id'].startswith('osm:') and hotel['evidence']
        for item in hotel['evidence']:
            assert item['url'].startswith('https://') and len(item['quote'].split()) <= 15
