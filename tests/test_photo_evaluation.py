from scripts.evaluate_photos import evaluate


def feature(key, value, details, flags=()):
    return {'hotel_id': 'h', 'feature_key': key, 'value': value, 'quality_flags': list(flags),
            'evidence': {'details': details}}


def test_photo_checks_count_inputs_separately_from_tests():
    base = {'best_sunset': {'sunset_over_sea_months': [1]}, 'vegetation_horizon_share_floor1': .2,
            'best_mountain': {'mountain_peak_m': 2900}}
    features = [feature('sea_view_potential', 'wide', {'levels': 4, 'levels_source': 'photo_verified', 'base': base}),
                feature('sunset_view_potential', 'year_round', {'base': base}),
                feature('mountain_view_potential', 'wide', {'base': base})]
    photos = {'observations': [
        {'hotel_id': 'h', 'name': 'H', 'url': 'u', 'levels': 4, 'levels_certainty': 'exact'},
        {'hotel_id': 'h', 'name': 'H', 'url': 'u', 'sea': True, 'floor_hint': 'upper', 'sunset_over_sea': True,
         'mountains': True, 'snow_peaks': True, 'trees_block_view': True}]}
    report = evaluate(photos, features)
    assert report['fixed_inputs'] == 1 and report['total'] == 5 and report['passed'] == 5
