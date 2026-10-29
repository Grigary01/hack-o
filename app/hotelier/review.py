"""Кабинет отельера: что система узнала об отеле, подтверждение/исправление, разрешение конфликтов.

Ничего не перезаписывается. Подтверждение или исправление отельера — новое
свидетельство (в демо — hotelier_simulated). Если оно расходится с расчётом,
репозиторий фиксирует конфликт, и поиск не берёт ни одну версию, пока оператор
не решит. Решение записывается в таблицу решений по конфликтам (одно на конфликт) и,
для review-расхождений, как свидетельство operator_decision с выбранной версией,
отвергнутой версией и причиной; история остаётся целиком.
"""
import uuid
from datetime import timedelta
from app.features.registry import get_registry
from app.features.service import MODEL_SOURCES, resolve_feature
from app.schemas.hotel import Observation, Evidence, Source
from app.storage.repository import now_utc


def hotel_facts(repo, hotel_id):
    """Текущие факты об отеле (уровень отеля), с объяснением и источником."""
    repo.hotel(hotel_id)
    observations = repo.observations(hotel_id)
    facts = []
    for key, definition in get_registry().definitions.items():
        if definition.scope != 'hotel':
            continue
        state = resolve_feature(observations, hotel_id, key, include_simulated=True)
        if not state.observations:
            continue
        model = [o for o in state.observations if o.evidence.source.type in MODEL_SOURCES]
        newest = max(state.observations, key=lambda o: o.collected_at)
        explanation = next((o.evidence.details.get('explanation') for o in sorted(
            model, key=lambda o: o.collected_at, reverse=True) if o.evidence.details.get('explanation')), None)
        facts.append({'feature_key': key, 'label': definition.label, 'value': state.value,
                      'display': None if state.value is None else definition.display(state.value),
                      'status': state.status, 'confidence_level': newest.confidence_level,
                      'explanation': explanation or definition.description,
                      'choices': definition.choices, 'type': definition.type, 'unit': definition.unit,
                      'reviewed_by_hotelier': any(o.evidence.method == 'hotelier_review' for o in state.observations),
                      'observation_ids': [o.id for o in state.observations]})
    return facts


def review_fact(repo, hotel_id, feature_key, verdict, value=None, comment=''):
    definition = get_registry().get(feature_key)
    if definition.scope != 'hotel':
        raise ValueError('Через проверку фактов правятся только характеристики отеля; номера — через вопросы')
    observations = repo.observations(hotel_id, feature_key)
    current = resolve_feature(observations, hotel_id, feature_key, include_simulated=True)
    model = [o for o in observations if o.evidence.source.type in MODEL_SOURCES and o.value is not None]
    if not model:
        raise ValueError('Для этой характеристики нет расчёта, который можно подтвердить')
    reviewed = max(model, key=lambda o: o.collected_at)
    if verdict == 'confirm':
        value = reviewed.value
    elif value is None:
        raise ValueError('Для исправления укажите новое значение')
    get_registry().validate_value(feature_key, value)
    now = now_utc()
    observation = Observation(
        id='review:' + uuid.uuid4().hex, hotel_id=hotel_id, subject_type='hotel', subject_id=hotel_id,
        feature_key=feature_key, value=value, unit=definition.unit, observed_at=now, collected_at=now,
        expires_at=now + timedelta(days=definition.ttl_days), status='estimated', confidence_level='low',
        confidence_method='Утверждение отельера (демо); независимо не проверено.',
        quality_flags=['simulated', 'hotelier_claim_not_independently_verified'],
        evidence=Evidence(source=Source(type='hotelier_simulated', name='Отельер (демо)', ref=reviewed.id),
                          method='hotelier_review', raw_excerpt=comment,
                          details={'verdict': verdict, 'reviewed_observation_id': reviewed.id,
                                   'previous_value': current.value, 'comment': comment}))
    repo.save_observation(observation)
    if value != reviewed.value:
        # Демо-ответ не спорит с реальными данными автоматически (разные «миры»),
        # поэтому расхождение с расчётом фиксируем явно — его разберёт оператор.
        repo.add_review_conflict(hotel_id, hotel_id, feature_key, observation.id, reviewed.id, 'hotelier_correction')
    return {'observation_id': observation.id, 'verdict': verdict, 'value': value,
            'conflicts': [c for c in repo.conflicts(hotel_id) if observation.id in (c['left_id'], c['right_id'])]}


def record_operator_decision(repo, conflict_id, chosen_observation_id, reason):
    """Свидетельство operator_decision для review-конфликта.

    Выбор и идемпотентность проверяет repo.resolve_conflict (таблица решений);
    здесь — значение, которое увидят поиск и кабинет.
    """
    conflict = repo.conflict(conflict_id)
    if chosen_observation_id not in (conflict['left_id'], conflict['right_id']):
        raise ValueError('Выберите одну из двух версий этого конфликта')
    chosen = repo.observation(chosen_observation_id)
    rejected = repo.observation(conflict['right_id'] if chosen_observation_id == conflict['left_id'] else conflict['left_id'])
    definition = get_registry().get(conflict['feature_key'])
    # Расхождение «номер против расчёта по зданию»: если прав расчёт, утверждение о номере не подтверждается.
    value = chosen.value if chosen.feature_key == conflict['feature_key'] else False
    now = now_utc()
    decision = Observation(
        id='decision:' + uuid.uuid4().hex, hotel_id=conflict['hotel_id'],
        subject_type='room' if ':room:' in conflict['subject_id'] else 'hotel', subject_id=conflict['subject_id'],
        feature_key=conflict['feature_key'], value=value, unit=definition.unit,
        observed_at=now, collected_at=now, expires_at=now + timedelta(days=definition.ttl_days),
        status=chosen.status if chosen.status in ('verified', 'estimated') else 'estimated',
        confidence_level=chosen.confidence_level if chosen.confidence_level != 'unknown' else 'low',
        confidence_method='Решение оператора по конфликту: выбрана одна версия, причина записана.',
        quality_flags=['operator_decision'],
        evidence=Evidence(source=Source(type='operator_decision', name='Оператор (демо)', ref=conflict_id),
                          method='operator_resolution', raw_excerpt=reason,
                          details={'conflict_id': conflict_id, 'chosen_observation_id': chosen.id,
                                   'rejected_observation_id': rejected.id, 'reason': reason,
                                   'policy': conflict['policy'],
                                   'simulated': 'hotelier_simulated' in (chosen.evidence.source.type,
                                                                         rejected.evidence.source.type)}))
    repo.save_observation(decision)
    return {'decision_observation_id': decision.id, 'value': value, 'conflict_id': conflict_id}
