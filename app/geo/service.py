"""Geo tools возвращают Observation с исходной датой snapshot, а не сегодняшним TTL."""
import hashlib
import json
import numpy as np
from dataclasses import asdict
from datetime import datetime, timedelta
from app.core.config import settings
from app.features.registry import get_registry
from app.schemas.hotel import Observation, Evidence, Source
from app.geo.osm_provider import fetch_osm_pois
from app.geo.routing import PedestrianRouter, load_walking_graph
from app.geo.quietness import calculate_quietness_proxy
from app.geo.viewshed import ViewshedScene, analyze_hotel
from app.geo.aircraft import runways, exposure, explanation as aircraft_explanation
from app.geo import route_quality, night

VIEWSHED_KEYS = ('sea_view_potential', 'sea_view_min_floor', 'sunset_view_potential', 'sunset_view_min_floor',
                 'mountain_view_potential', 'mountain_view_min_floor')
AIRCRAFT_KEYS = ('aircraft_noise_exposure', 'aircraft_path_distance_m')
ROUTE_KEYS = ('beach_route_climb_m', 'beach_route_busy_crossings')
NIGHT_KEYS = ('night_open_places_500m', 'nearest_night_pharmacy_m')


class GeoService:
    def __init__(self, directory=settings.demo_dir, environment_dir=settings.environment_dir):
        self.directory = directory
        self.environment_dir = environment_dir
        self.viewshed_scene = None
        self.viewshed_cache = {}
        self.snapshot = json.loads((directory/'osm_snapshot.json').read_text())
        self.graph_metadata = json.loads((directory/'graph_metadata.json').read_text())
        self.region = json.loads((directory/'region.json').read_text())
        self.router = None

    def _router(self):
        if self.router is None:
            graph = load_walking_graph(self.directory/'walk.graphml')
            self.router = PedestrianRouter(graph, fetch_osm_pois(self.snapshot,'beaches'),
                                          fetch_osm_pois(self.snapshot,'barriers'),
                                          self.region['max_hotel_snap_m'], self.region['max_beach_snap_m'])
        return self.router

    def _scene(self):
        if self.viewshed_scene is None:
            self.viewshed_scene = ViewshedScene.load(self.environment_dir,
                                                     self.region['hotel_bbox_south_west_north_east'])
        return self.viewshed_scene

    def compute_aircraft(self, hotel, feature_key):
        definition = get_registry().get(feature_key)
        raw = json.loads((self.environment_dir/'osm_aeroways.json').read_text())
        scene = self._scene()
        ground = lambda x, y: float(scene.dem_grid.bilinear(scene.dtm, np.array([x]), np.array([y]))[0])
        category, details = exposure(hotel.lat, hotel.lon, runways(raw['elements']), ground)
        nearest = details.get('nearest')
        value = category if feature_key == 'aircraft_noise_exposure' else (
            float(nearest['slant_m']) if nearest else None)
        metadata = raw['metadata']
        observed = datetime.fromisoformat(metadata['osm_base'].replace('Z', '+00:00'))
        collected = datetime.fromisoformat(metadata['collected_at'])
        if nearest:
            details['explanation'] = aircraft_explanation(nearest)
        details = details | {'inputs': {'aeroways': {'path': 'data/environment/osm_aeroways.json',
                                                    'query_sha256': metadata['query_sha256'],
                                                    'osm_base': metadata['osm_base']},
                                       'dem': scene.inputs['dem']}}
        digest = hashlib.sha256(json.dumps([hotel.id, feature_key, metadata['query_sha256'], scene.inputs['dem']['sha256'],
                                            value, details], sort_keys=True, default=str).encode()).hexdigest()
        return Observation(id=digest, hotel_id=hotel.id, subject_type='hotel', subject_id=hotel.id,
            feature_key=feature_key, value=value, unit=definition.unit,
            observed_at=observed, collected_at=collected, expires_at=observed+timedelta(days=definition.ttl_days),
            status='estimated' if value is not None else 'unknown',
            confidence_level='low' if value is not None else 'unknown',
            confidence_method=('Геометрия ВПП из OSM и прямые траектории с глиссадой 3°; без реальных треков, '
                               'расписания и загрузки полос. Не дБ; вероятность не оценивалась.'),
            quality_flags=['osm_coverage_not_field_verified', 'uncalibrated_model'] + details.get('limits', []),
            evidence=Evidence(source=Source(type='geo_model', name='OSM ВПП аэропорта Сочи + Copernicus DEM GLO-30',
                ref=metadata['query_sha256'], url=hotel.source_url), method='aircraft_track_proximity_v1',
                snapshot_path='data/environment/osm_aeroways.json', details=details))

    def compute_night(self, hotel, feature_key):
        definition = get_registry().get(feature_key)
        raw = json.loads((self.environment_dir/'osm_amenities.json').read_text())
        summary = night.summarize(hotel, raw['elements'])
        if feature_key == 'night_open_places_500m':
            value, text = summary['night_count'], night.explain_places(summary)
        else:
            nearest = summary['nearest_night_pharmacy']
            value, text = (float(nearest['distance_m']) if nearest else None), night.explain_pharmacy(summary)
        metadata = raw['metadata']
        observed = datetime.fromisoformat(metadata['osm_base'].replace('Z', '+00:00'))
        collected = datetime.fromisoformat(metadata['collected_at'])
        details = summary | {'explanation': text}
        digest = hashlib.sha256(json.dumps([hotel.id, feature_key, metadata['query_sha256'], value, details],
                                           sort_keys=True, default=str).encode()).hexdigest()
        return Observation(id=digest, hotel_id=hotel.id, subject_type='hotel', subject_id=hotel.id,
            feature_key=feature_key, value=value, unit=definition.unit,
            observed_at=observed, collected_at=collected, expires_at=observed+timedelta(days=definition.ttl_days),
            status='estimated' if value is not None else 'unknown',
            confidence_level='low' if value is not None else 'unknown',
            confidence_method=('Часы работы из OSM opening_hours (их ведут волонтёры, могут устареть); '
                               'расстояние по прямой. Вероятность не оценивалась.'),
            quality_flags=['osm_coverage_not_field_verified', 'opening_hours_may_be_outdated', 'straight_line_distance'] +
                          (['many_places_without_hours'] if summary['unknown_hours_in_radius'] > summary['places_in_radius'] / 2 else []),
            evidence=Evidence(source=Source(type='openstreetmap', name='OpenStreetMap contributors',
                ref=metadata['query_sha256'], url=hotel.source_url), method='opening_hours_v1',
                snapshot_path='data/environment/osm_amenities.json', details=details))

    def compute_route_quality(self, hotel, feature_key):
        """Тот же маршрут, что для расстояния до пляжа, плюс рельеф и дороги OSM."""
        definition = get_registry().get(feature_key)
        scene = self._scene()
        ground = lambda x, y: float(scene.dem_grid.bilinear(scene.dtm, np.array([x]), np.array([y]))[0])
        route = self._router().distance_to_beach(hotel)
        result = route_quality.analyze(route, self._router().graph, self.snapshot['elements'], ground)
        metadata = self.snapshot['metadata']
        observed = datetime.fromisoformat(metadata.get('osm_base') or metadata['collected_at'])
        collected = datetime.fromisoformat(metadata['collected_at'])
        if result is None:
            value, details = None, {'reason': route.reason or 'no_route'}
        else:
            value = result['climb_m'] if feature_key == 'beach_route_climb_m' else result['busy_crossings']
            details = result | {'explanation': route_quality.explain_climb(result) if feature_key == 'beach_route_climb_m'
                                else route_quality.explain_crossings(result),
                                'beach_id': route.beach_id, 'graph_sha256': self.graph_metadata['sha256'],
                                'dem_sha256': scene.inputs['dem']['sha256']}
        digest = hashlib.sha256(json.dumps([hotel.id, feature_key, metadata['query_sha256'], self.graph_metadata['sha256'],
                                            scene.inputs['dem']['sha256'], value, details], sort_keys=True,
                                           default=str).encode()).hexdigest()
        return Observation(id=digest, hotel_id=hotel.id, subject_type='hotel', subject_id=hotel.id,
            feature_key=feature_key, value=value, unit=definition.unit,
            observed_at=observed, collected_at=collected, expires_at=observed+timedelta(days=definition.ttl_days),
            status='estimated' if value is not None else 'unknown',
            confidence_level='low' if value is not None else 'unknown',
            confidence_method=('Маршрут по графу OSM; рельеф GLO-30 (±2–4 м), тип перехода — по тегам OSM; '
                               'на местности не проверено. Вероятность не оценивалась.'),
            quality_flags=['osm_coverage_not_field_verified'] + (result or {}).get('limits', []) +
                          ([route.reason] if route.reason else []),
            evidence=Evidence(source=Source(type='geo_model', name='OSM пешеходный граф и дороги + Copernicus DEM GLO-30',
                ref=metadata['query_sha256'], url=hotel.source_url), method='route_quality_v1',
                snapshot_path='data/demo/osm_snapshot.json', details=details))

    def _viewshed(self, hotel):
        """Один расчёт на отель даёт все четыре характеристики вида."""
        if hotel.id not in self.viewshed_cache:
            self.viewshed_cache[hotel.id] = analyze_hotel(self._scene(), hotel)
        return self.viewshed_cache[hotel.id]

    def compute_viewshed(self, hotel, feature_key):
        definition = get_registry().get(feature_key)
        result = self._viewshed(hotel)
        scene = self.viewshed_scene
        # Дата знания — состояние зданий OSM: именно их изменения закрывают вид.
        observed = datetime.fromisoformat(scene.inputs['buildings']['osm_base'].replace('Z', '+00:00'))
        collected = datetime.fromisoformat(scene.inputs['coastline']['osm_base'].replace('Z', '+00:00'))
        collected = max(collected, observed)
        flags = ['osm_coverage_not_field_verified', 'uncalibrated_model']
        if result['status'] != 'computed':
            value, details, level = None, result, 'unknown'
            flags.append(result['reason'])
            method_text = 'Расчёт невозможен: ' + result['reason']
        else:
            value = result['base'][feature_key]
            flags += result['limits']
            # Устойчивость считаем по своей «семье» (море/закат/горы), а не по всем сразу.
            robust = result['robust_by_family'][feature_key.split('_view')[0]]
            if result['building_match'] != 'osm_id' and result['building_match'] != 'contains_hotel_point':
                flags.append('hotel_building_matched_by_proximity')
            if not robust:
                flags.append('sensitive_to_unknown_building_heights')
            # medium только если вывод не меняется при любых допущениях о неизвестных высотах
            # и этажность самого отеля известна из OSM. high без проверки на месте не ставим.
            level = ('medium' if robust and result['levels_source'] == 'osm_building_levels'
                     and 'hotel_building_matched_by_proximity' not in flags else 'low')
            if value is None:
                level = 'unknown'
            details = {k: v for k, v in result.items() if k != 'scenarios'} | {
                'scenarios': result['scenarios'], 'summary': result['base']['summary'],
                'explanation': result['base']['summary_' + feature_key.split('_view')[0]]}
            method_text = ('Перебор неизвестных высот соседних зданий (3, 6.5, 12 м): '
                           + ('вывод одинаков во всех сценариях' if robust
                              else 'вывод зависит от допущения') + '; этажность отеля: ' + result['levels_source']
                           + '. Вероятность не оценивалась.')
        digest = hashlib.sha256(json.dumps([hotel.id, feature_key, scene.fingerprint(), str(observed), value,
                                            details], sort_keys=True, default=str).encode()).hexdigest()
        return Observation(id=digest, hotel_id=hotel.id, subject_type='hotel', subject_id=hotel.id,
            feature_key=feature_key, value=value, unit=definition.unit,
            observed_at=observed, collected_at=collected, expires_at=observed+timedelta(days=definition.ttl_days),
            status='estimated' if value is not None else 'unknown', confidence_level=level,
            confidence_method=method_text, quality_flags=flags,
            evidence=Evidence(source=Source(type='geo_model', name='OSM здания и coastline + Copernicus DEM GLO-30',
                ref=scene.fingerprint(), url=hotel.source_url), method='viewshed_v1',
                snapshot_path='data/environment/osm_buildings.json', details=details))

    def compute(self, hotel, feature_key):
        if feature_key in VIEWSHED_KEYS:
            return self.compute_viewshed(hotel, feature_key)
        if feature_key in AIRCRAFT_KEYS:
            return self.compute_aircraft(hotel, feature_key)
        if feature_key in ROUTE_KEYS:
            return self.compute_route_quality(hotel, feature_key)
        if feature_key in NIGHT_KEYS:
            return self.compute_night(hotel, feature_key)
        definition = get_registry().get(feature_key)
        metadata = self.snapshot['metadata']
        observed = datetime.fromisoformat(metadata.get('osm_base') or metadata['collected_at'])
        collected = datetime.fromisoformat(metadata['collected_at'])
        flags = ['osm_coverage_not_field_verified']
        if feature_key == 'walking_distance_to_beach_m':
            result = self._router().distance_to_beach(hotel)
            value = round(result.distance_m,1) if result.distance_m is not None else None
            details = asdict(result) | {'graph_snapshot_date':self.graph_metadata['collected_at'],
                                       'graph_sha256':self.graph_metadata['sha256'],
                                       'coverage_quality':'approximate_entries'}
            flags += result.flags + ([result.reason] if result.reason else [])
            method = 'pedestrian_graph'
        elif feature_key in ('quietness_proxy','nightlife_distance_m'):
            quietness,nightlife,details = calculate_quietness_proxy(hotel,self.snapshot['elements'])
            value = quietness if feature_key == 'quietness_proxy' else (round(nightlife[0],1) if nightlife else None)
            details['nearest_nightlife'] = nightlife
            method = 'noise_proxy_v1' if feature_key == 'quietness_proxy' else 'projected_distance_to_osm_geometry'
            flags += ['uncalibrated_heuristic','aircraft_noise_not_modeled']
        else:
            raise ValueError(f'Geo calculator не реализован: {feature_key}')
        digest = hashlib.sha256(json.dumps([hotel.id,feature_key,metadata['query_sha256'],
                                           self.graph_metadata['sha256'],str(observed),value,details],sort_keys=True).encode()).hexdigest()
        return Observation(id=digest, hotel_id=hotel.id,subject_type='hotel',subject_id=hotel.id,
            feature_key=feature_key,value=value,unit=definition.unit,
            observed_at=observed,collected_at=collected,expires_at=observed+timedelta(days=definition.ttl_days),
            status='estimated' if value is not None else 'unknown',confidence_level='low' if value is not None else 'unknown',
            confidence_method='Эвристический уровень: полнота OSM и входы не проверены на местности; вероятность не оценивалась.',
            quality_flags=flags,evidence=Evidence(source=Source(type='openstreetmap',name='OpenStreetMap contributors',
            ref=metadata['query_sha256'],url=hotel.source_url),method=method,snapshot_path='data/demo/osm_snapshot.json',details=details))
