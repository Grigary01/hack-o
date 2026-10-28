"""Текущее знание — представление над неизменяемой историей наблюдений."""
from dataclasses import dataclass, field
from collections.abc import Sequence
from itertools import combinations
from app.schemas.conflicts import Conflict
from app.storage.repository import now_utc


@dataclass
class FeatureState:
    subject_id: str
    feature_key: str
    value: object = None
    status: str = 'unknown'
    observations: list = field(default_factory=list)
    resolved_conflict_ids: list[str] = field(default_factory=list)


MODEL_SOURCES = ('openstreetmap', 'geo_model')


def supersedes(newer, older):
    """Пересчёт той же модели по более новому снимку данных заменяет старый результат.

    Это не конфликт источников: OSM/рельеф обновились, расчёт повторён тем же
    методом. Противоречия между разными источниками (отельер, другая модель) остаются.
    """
    return (newer.evidence.source.type in MODEL_SOURCES and
            newer.evidence.source.type == older.evidence.source.type and
            newer.evidence.method == older.evidence.method and
            (newer.observed_at, newer.collected_at) > (older.observed_at, older.collected_at))


def is_simulated(observation):
    """Демо-ответ отельера или решение оператора по демо-ответу не попадает в реальный поиск."""
    return (observation.evidence.source.type == 'hotelier_simulated' or
            (observation.evidence.source.type == 'operator_decision' and observation.evidence.details.get('simulated')))


def apply_decisions(observations):
    """Решение оператора по конфликту заменяет все версии, известные на момент решения.
    Более позднее свидетельство снова участвует — новый конфликт будет замечен."""
    decisions = [x for x in observations if x.evidence.source.type == 'operator_decision']
    if not decisions:
        return observations
    decision = max(decisions, key=lambda x: x.collected_at)
    return [decision] + [x for x in observations if x is not decision and
                         x.evidence.source.type != 'operator_decision' and x.collected_at > decision.collected_at]


def latest_snapshots(observations):
    return [x for x in observations if not any(supersedes(y, x) for y in observations if y is not x)]


def resolve_feature(observations, subject_id, feature_key, include_simulated=False, now=None,
                    *, conflicts: Sequence[Conflict] = ()):
    """Возвращает одно допустимое сейчас значение для ranker и историю.

    Это про достоверность данных, а не про важность пожелания пользователя.
    Например, старое sea_view=True не должно пройти новое обязательное условие.
    """
    now = now or now_utc()
    # Сначала нужный объект/признак; учебные утверждения выключены по умолчанию.
    rows = [x for x in observations if x.subject_id==subject_id and x.feature_key==feature_key
            and (include_simulated or not is_simulated(x))]
    # Истёкшие и будущие значения не являются текущим знанием.
    active = [x for x in rows if x.observed_at <= now < x.expires_at and x.value is not None
              and x.status not in ('unknown','stale')]
    active = apply_decisions(latest_snapshots(active))
    state = FeatureState(subject_id,feature_key,observations=rows)
    if not active:
        state.status = 'stale' if rows and all(x.expires_at <= now for x in rows) else 'unknown'
        return state
    if any(x.status == 'conflicted' for x in active):
        state.status = 'conflicted'
        return state

    by_id = {o.id: o for o in rows}
    active_ids = {o.id for o in active}
    decisions, selected_ids, rejected_ids = {}, set(), set()
    for conflict in conflicts:
        resolution = conflict.resolution
        if (conflict.subject_id != subject_id or conflict.feature_key != feature_key
                or resolution is None or resolution.resolved_at > now
                or resolution.conflict_id != conflict.id):
            continue
        left, right = by_id.get(conflict.left_id), by_id.get(conflict.right_id)
        if left is None or right is None or not ({left.id, right.id} & active_ids):
            continue
        if ((left.hotel_id, left.subject_id, left.feature_key)
                != (conflict.hotel_id, subject_id, feature_key)
                or (right.hotel_id, right.subject_id, right.feature_key)
                != (conflict.hotel_id, subject_id, feature_key)
                or left.value == right.value
                or (left.evidence.source.type == 'hotelier_simulated')
                   != (right.evidence.source.type == 'hotelier_simulated')
                or resolution.selected_observation_id not in (left.id, right.id)):
            continue
        pair = frozenset((left.id, right.id))
        selected = resolution.selected_observation_id
        if pair in decisions and decisions[pair] != selected:
            state.status = 'conflicted'
            return state
        decisions[pair] = selected
        selected_ids.add(selected)
        rejected_ids.update(pair - {selected})
        state.resolved_conflict_ids.append(conflict.id)

    # Каждая пара противоречащих активных свидетельств требует своего решения.
    # Старое решение не распространяется на новый ответ, даже с тем же значением.
    if selected_ids & rejected_ids or any(
            left.value != right.value and frozenset((left.id, right.id)) not in decisions
            for left, right in combinations(active, 2)):
        state.status = 'conflicted'
        return state
    remaining = [o for o in active if o.id not in rejected_ids]
    if not remaining:
        # Отвергнутое свидетельство не воскресает, когда выбранное устарело.
        state.status = 'stale' if any(by_id[oid].expires_at <= now for oid in selected_ids) else 'unknown'
        return state
    newest = max(remaining, key=lambda x: x.collected_at)
    state.value, state.status = newest.value, newest.status
    state.resolved_conflict_ids.sort()
    return state
