"""Проверяет реальные IDs, snapshot, checksum графа и воспроизводимость всех Geo-значений."""
import hashlib
import json
from datetime import datetime, timezone
from collections import Counter
from app.core.config import settings
from app.geo.service import GeoService
from app.geo.osm_provider import fetch_osm_hotels
from app.schemas.hotel import Hotel, Observation


def main():
    root=settings.demo_dir
    raw=json.loads((root/'osm_snapshot.json').read_text())
    region=json.loads((root/'region.json').read_text())
    hotels=[Hotel.model_validate(x) for x in json.loads((root/'hotels.json').read_text())]
    features=[Observation.model_validate(x) for x in json.loads((root/'features.json').read_text())]
    graph_metadata=json.loads((root/'graph_metadata.json').read_text())
    assert hashlib.sha256((root/'walk.graphml').read_bytes()).hexdigest()==graph_metadata['sha256']
    assert [h.model_dump(mode='json') for h in hotels]==[Hotel.model_validate(h).model_dump(mode='json') for h in fetch_osm_hotels(raw,region)]
    assert 15<=len(hotels)<=30 and len({h.id for h in hotels})==len(hotels)
    geo=GeoService(root)
    by_id={h.id:h for h in hotels}
    for old in features:
        recomputed=geo.compute(by_id[old.hotel_id],old.feature_key)
        assert old.model_dump(mode='json')==recomputed.model_dump(mode='json'),old.id
    routes=[o for o in features if o.feature_key=='walking_distance_to_beach_m']
    successful=[o for o in routes if o.value is not None]
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'hotels':len(hotels),
        'osm_elements':len(raw['elements']),'graph_nodes':graph_metadata['nodes'],'graph_edges':graph_metadata['edges'],
        'observations':len(features),'routes_computed':len(successful),'route_coverage':len(successful)/len(hotels),
        'unknown_routes':[{ 'hotel_id':o.hotel_id,'reason':o.evidence.details['reason']} for o in routes if o.value is None],
        'all_observations_recomputed':True,'graph_checksum_valid':True,
        'confidence_levels':dict(Counter(o.confidence_level for o in features)),
        'ground_truth_accuracy':None,'field_survey_done':False,
        'note':'Проверены происхождение и воспроизводимость, не существование/проходимость на местности.'}
    (root/'quality_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
