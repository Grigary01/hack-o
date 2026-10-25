"""Прозрачная, НЕ калиброванная модель внешних источников шума.

risk=max(weight*exp(-d/scale)). Уровни high quietness <.25, medium <.6,
иначе low. Геометрия линии учитывается, а не только центр дороги.
"""
import math
from app.geo.geometry import metric_point, element_shape
from app.geo.osm_provider import osm_id

ROAD_WEIGHTS = {'motorway':1, 'trunk':1, 'primary':.9, 'secondary':.7,
                'tertiary':.5, 'residential':.3, 'service':.15, 'unclassified':.4}


def calculate_quietness_proxy(hotel, elements):
    point = metric_point(hotel.lat, hotel.lon)
    contributors = []
    nightlife_distances = []
    for item in elements:
        tags = item.get('tags',{})
        if tags.get('railway') == 'rail':
            weight,scale,kind = 1.,180.,'rail'
        elif tags.get('amenity') in ('bar','pub','nightclub'):
            weight,scale,kind = .6,100.,'nightlife'
        elif tags.get('highway') in ROAD_WEIGHTS:
            weight,scale,kind = ROAD_WEIGHTS[tags['highway']],120.,'road'
        else:
            continue
        shape = element_shape(item)
        if shape is None:
            continue
        distance = point.distance(shape)
        if kind == 'nightlife':
            nightlife_distances.append((distance, osm_id(item)))
        risk = weight * math.exp(-distance / scale)
        contributors.append({'osm_id':osm_id(item),'kind':kind,'distance_m':round(distance,1),
                             'weight':weight,'decay_scale_m':scale,'risk':round(risk,4)})
    contributors.sort(key=lambda x:x['risk'],reverse=True)
    risk = contributors[0]['risk'] if contributors else None
    quietness = None if risk is None else ('high' if risk < .25 else 'medium' if risk < .6 else 'low')
    nearest_nightlife = min(nightlife_distances) if nightlife_distances else None
    return quietness, nearest_nightlife, {'risk':risk, 'top_contributors':contributors[:5],
        'formula':'max(weight * exp(-distance_m / decay_scale_m))',
        'limits':'Не дБ; без авиации, сезонности, строек, окон и реального акустического измерения.'}
