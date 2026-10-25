"""Geo tools возвращают Observation с исходной датой snapshot, а не сегодняшним TTL."""
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timedelta
from app.core.config import settings
from app.features.registry import get_registry
from app.schemas.hotel import Observation, Evidence, Source
from app.geo.osm_provider import fetch_osm_pois
from app.geo.routing import PedestrianRouter, load_walking_graph
from app.geo.quietness import calculate_quietness_proxy


class GeoService:
    def __init__(self, directory=settings.demo_dir):
        self.directory = directory
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

    def compute(self, hotel, feature_key):
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
