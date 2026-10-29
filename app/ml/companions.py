"""Расширение распознанного запроса расчётными характеристиками-спутниками.

Гость говорит «вид на море»; парсер честно извлекает желание про номер
(sea_view, room) — его подтверждает только отельер. Но у нас есть и расчёт
по зданию: с какого этажа и с какой стороны видно море. Чтобы поиск его
использовал, backend добавляет мягкое пожелание sea_view_potential.

Связи описаны в registry.yaml (companions), не в коде: новая пара
«желание → расчёт» добавляется текстом. Hard-условие гостя спутник не
ужесточает: расчёт по зданию не доказывает вид из конкретного номера,
поэтому спутник всегда только мягкое пожелание.
"""
from app.features.registry import get_registry
from app.schemas.query import ParsedHotelQuery, SoftPreference

MAX_PREFERENCES = 12


def _desired(companion, parent_value):
    if isinstance(parent_value, bool):
        chosen = companion.desired_if_true if parent_value else companion.desired_if_false
        return chosen if chosen is not None else companion.desired
    return companion.desired


def expand(parsed: ParsedHotelQuery) -> ParsedHotelQuery:
    registry = get_registry()
    result = parsed.model_copy(deep=True)
    # Автоматические веса пересчитываем от актуального родителя. Явный выбор
    # пользователя сохраняем, даже если этот признак первоначально добавлен нами.
    result.soft_preferences = [p for p in result.soft_preferences if p.weight_source != 'companion']
    present = {p.feature_key for p in result.soft_preferences}
    parents = []
    for hard in result.hard_constraints:
        if hard.operator in ('=', '!=') and isinstance(hard.value, bool):
            value = hard.value if hard.operator == '=' else not hard.value
            parents.append((hard.feature_key, value, None))
    for pref in result.soft_preferences:
        if pref.derived_from is None:
            parents.append((pref.feature_key, pref.desired, pref.importance))
    for key, value, importance in parents:
        for companion in registry.get(key).companions:
            desired = _desired(companion, value)
            if desired is None or companion.feature_key in present or len(result.soft_preferences) >= MAX_PREFERENCES:
                continue
            base = importance if importance is not None else registry.get(companion.feature_key).default_weight
            result.soft_preferences.append(SoftPreference(
                feature_key=companion.feature_key, desired=desired, scope='hotel',
                importance=round(base * companion.weight_factor, 3),
                weight_source='companion', derived_from=key))
            present.add(companion.feature_key)
    return result
