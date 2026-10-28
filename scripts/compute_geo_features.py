import json
from app.core.config import settings
from app.geo.service import GeoService, VIEWSHED_KEYS, AIRCRAFT_KEYS, ROUTE_KEYS, NIGHT_KEYS, FACADE_KEYS
from app.schemas.hotel import Hotel


def main():
    geo = GeoService()
    hotels = [Hotel.model_validate(x) for x in json.loads((settings.demo_dir/'hotels.json').read_text())]
    features = [geo.compute(h,key).model_dump(mode='json') for h in hotels for key in
                ('walking_distance_to_beach_m','quietness_proxy','nightlife_distance_m',*VIEWSHED_KEYS,*AIRCRAFT_KEYS,*ROUTE_KEYS,*NIGHT_KEYS,*FACADE_KEYS)]
    (settings.demo_dir/'features.json').write_text(json.dumps(features,ensure_ascii=False,indent=2))
    routes = [f for f in features if f['feature_key']=='walking_distance_to_beach_m']
    print(json.dumps({'hotels':len(hotels),'observations':len(features),
                      'routes':sum(f['value'] is not None for f in routes),
                      'reasons':[f['quality_flags'] for f in routes if f['value'] is None]},ensure_ascii=False))


if __name__ == '__main__':
    main()
