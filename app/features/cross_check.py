"""Сверка утверждения отельера о номере с расчётом по зданию (registry.model_check).

Отельер: «в номере 201 (2-й этаж) вид на море». Расчёт: «море видно только
с 3-го этажа» или «моря не видно ни с одного этажа». Это расхождение разных
источников о разных уровнях детализации: номер против здания. Мы не выбираем
победителя автоматически — у отельера конкретика, у модели известные пробелы
(деревья, неизвестные высоты). Значение отельера остаётся, а поиск и кабинет
показывают расхождение и просят перепроверить.

«Нет вида» в номере расчёту не противоречит: здание может видеть море
другими окнами. Поэтому проверяются только утверждения True.
"""
from app.features.registry import get_registry
from app.features.service import resolve_feature


def model_disagreements(observations, hotel_id, room_subject_id, feature_key,
                        include_simulated=False, now=None, *, conflicts=()):
    """Список расхождений для текущего значения отельера о номере (может быть пуст)."""
    definition = get_registry().get(feature_key)
    check = definition.model_check
    if check is None or room_subject_id is None:
        return []
    claim = resolve_feature(observations, room_subject_id, feature_key, include_simulated, now, conflicts=conflicts)
    if claim.value is not True:
        return []
    decisions = [o for o in claim.observations if o.evidence.source.type == 'operator_decision']
    if decisions:
        decision = max(decisions, key=lambda o: o.collected_at)
        newer = [o for o in claim.observations if o.collected_at > decision.collected_at
                 and o.evidence.source.type != 'operator_decision']
        if decision.value == claim.value and not newer:
            return []  # оператор уже разобрал расхождение и оставил значение отельера
    potential = resolve_feature(observations, hotel_id, check.potential, include_simulated, now, conflicts=conflicts)
    if potential.value is None:
        return []
    claim_obs = max((o for o in claim.observations if o.value is True), key=lambda o: o.collected_at)
    model_obs = max(potential.observations, key=lambda o: o.collected_at)
    room = room_subject_id.split(':room:')[-1]
    floor = claim_obs.evidence.details.get('floor')
    hint = model_obs.evidence.details.get('explanation') or ''
    result = []
    if potential.value == check.none_value:
        result.append({'reason': 'model_sees_none', 'hotelier_observation_id': claim_obs.id,
                       'model_observation_id': model_obs.id,
                       'text': f'Отельер указал «{definition.label.lower()}» в номере {room}, '
                               f'а расчёт по зданию этого не видит. {hint}'.strip()})
    elif check.min_floor and floor is not None:
        min_floor = resolve_feature(observations, hotel_id, check.min_floor, include_simulated, now, conflicts=conflicts)
        if min_floor.value is not None and floor < min_floor.value:
            floor_obs = max(min_floor.observations, key=lambda o: o.collected_at)
            result.append({'reason': 'below_model_min_floor', 'hotelier_observation_id': claim_obs.id,
                           'model_observation_id': floor_obs.id,
                           'text': f'Отельер указал «{definition.label.lower()}» в номере {room} на {floor}-м этаже, '
                                   f'а по расчёту это видно только с {min_floor.value:g}-го этажа. {hint}'.strip()})
    return result
