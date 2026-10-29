"""Constrained planner: выбирает cache, Geo provider или вопрос по реестру.

Это наблюдаемый rule-based выбор источника, не LLM, знающая факты сама.
"""
from app.features.registry import get_registry
from app.features.service import resolve_feature
from app.geo.service import GeoService
from app.hotelier.dialogue import ask_hotelier
from app.agent.tool_registry import ToolSpec, ToolRegistry
from app.storage.repository import now_utc


class FeatureAgent:
    def __init__(self,repo,max_calls=100):
        self.repo = repo
        self.geo = None
        self.trace = []
        self.tools = ToolRegistry([
            ToolSpec('pedestrian_distance',self._compute),
            ToolSpec('quietness',self._compute),
            ToolSpec('nightlife_distance',self._compute),
            ToolSpec('viewshed',self._compute),
            ToolSpec('aircraft_noise',self._compute),
            ToolSpec('route_quality',self._compute),
            ToolSpec('night_amenities',self._compute),
            ToolSpec('facade_noise',self._compute),
            # Выводится из сохранённых сценариев расчёта вида, без новых геоданных.
            ToolSpec('view_robustness',self._derive_view_robustness),
            ToolSpec('hotelier',lambda p:ask_hotelier(repo,p.hotel_id,p.feature_key)),
        ],max_calls=max_calls)

    def _compute(self,params):
        if self.geo is None:
            self.geo = GeoService()
        observation = self.geo.compute(self.repo.hotel(params.hotel_id),params.feature_key)
        self.repo.save_observation(observation)
        return {'observation_id':observation.id,'status':observation.status,
                'snapshot_expired':observation.expires_at<=now_utc()}

    def _derive_view_robustness(self,params):
        from app.features.view_robustness import compute
        observation = compute(self.repo, params.hotel_id)
        self.repo.save_observation(observation)
        return {'observation_id':observation.id,'status':observation.status,
                'snapshot_expired':observation.expires_at<=now_utc()}

    def ensure(self,hotel_id,feature_key,include_simulated=False):
        definition = get_registry().get(feature_key)
        observations = self.repo.observations(hotel_id,feature_key)
        subject_ids = {o.subject_id for o in observations} if definition.scope=='room' else {hotel_id}
        conflicts = self.repo.conflict_records(hotel_id)
        if definition.provider == 'hotelier':
            self.repo.refresh_existing_question(hotel_id, feature_key)
        states = [resolve_feature(observations,s,feature_key,include_simulated,
                                  conflicts=conflicts) for s in subject_ids]
        entry = {'hotel_id':hotel_id,'feature_key':feature_key,'provider':definition.provider}
        if states and all(s.value is not None for s in states):
            entry.update(action='read_evidence',reason='fresh_known_observation')
        elif definition.scope=='hotel' and observations:
            # Повтор старого snapshot не создаёт свежих данных; unknown тоже не лечится пересчётом.
            entry.update(action='request_snapshot_refresh',reason='stale_unknown_or_conflicted_snapshot',
                         command='python -m scripts.refresh_geo --refresh')
        else:
            try:
                result = self.tools.execute(definition.provider,{'hotel_id':hotel_id,'feature_key':feature_key})
                entry.update(action='tool_call',tool_used=definition.provider,result=result,
                             reason='missing_or_conflicted_feature')
            except (ValueError,TimeoutError,OSError) as exc:
                entry.update(action='tool_error',error=str(exc))
        self.trace.append(entry)
        return entry
