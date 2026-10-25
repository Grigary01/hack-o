from frontend.map_view import offline_map,MapEngine


def test_osm_text_is_escaped_in_maps():
    hotel={'name':'<script>alert(1)</script>','lat':43.43,'lon':39.92}
    result={'hotel':hotel,'criteria':[]}
    assert '<script>alert(1)</script>' not in offline_map([result])
    engine=MapEngine([43.43,39.92]);engine.add_hotels([hotel])
    assert '<script>alert(1)</script>' not in engine.render()
