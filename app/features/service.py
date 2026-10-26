"""Текущее знание — представление над неизменяемой историей наблюдений."""
from dataclasses import dataclass, field
from app.storage.repository import now_utc


@dataclass
class FeatureState:
    subject_id: str
    feature_key: str
    value: object = None
    status: str = 'unknown'
    observations: list = field(default_factory=list)


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


def latest_snapshots(observations):
    return [x for x in observations if not any(supersedes(y, x) for y in observations if y is not x)]


def resolve_feature(observations, subject_id, feature_key, include_simulated=False, now=None):
    """Возвращает одно допустимое сейчас значение для ranker и историю.

    Это про достоверность данных, а не про важность пожелания пользователя.
    Например, старое sea_view=True не должно пройти новое обязательное условие.
    """
    now = now or now_utc()
    # Сначала нужный объект/признак; учебные утверждения выключены по умолчанию.
    rows = [x for x in observations if x.subject_id==subject_id and x.feature_key==feature_key
            and (include_simulated or x.evidence.source.type!='hotelier_simulated')]
    # Истёкшие и будущие значения не являются текущим знанием.
    active = [x for x in rows if x.observed_at <= now < x.expires_at and x.value is not None
              and x.status not in ('unknown','stale')]
    active = latest_snapshots(active)
    state = FeatureState(subject_id,feature_key,observations=rows)
    if not active:
        state.status = 'stale' if rows and all(x.expires_at <= now for x in rows) else 'unknown'
    elif any(x.status=='conflicted' for x in active) or len({(type(x.value).__name__,str(x.value)) for x in active}) > 1:
        # При конфликте не выбираем автоматически самый новый ответ:
        # value остаётся None, обе версии доступны в observations.
        state.status = 'conflicted'
    else:
        newest = max(active,key=lambda x:x.collected_at)
        state.value, state.status = newest.value,newest.status
    return state
