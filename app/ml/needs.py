"""Потребности гостя: каждая часть запроса учтена, ответ строится по ним.

Парсер (правила или LLM) размечает запрос на потребности с цитатами. Здесь backend:
1. дополняет то, что парсер не разметил: каждое условие hard/soft и каждая
   непроверяемая тема попадают в какую-то потребность — ничего не теряется молча;
2. раскрывает расплывчатые пожелания из concepts.yaml («вид из окна») в мягкие
   пожелания по всем вариантам; ранжирование берёт лучший (app/ml/multicriteria.py);
3. применяет уточнение гостя (choices: {"window_view": "sea"}) без нового разбора текста.

Функции идемпотентны: разобранный запрос из ответа можно отправить обратно.
"""
from app.features.concepts import get_concept
from app.features.registry import get_registry
from app.schemas.query import Need, NeedOption, ParsedHotelQuery, SoftPreference

MAX_PREFERENCES = 12


def _primary_keys(parsed: ParsedHotelQuery) -> list[str]:
    """Признаки, о которых просил гость (без расчётных спутников)."""
    keys = [h.feature_key for h in parsed.hard_constraints]
    keys += [p.feature_key for p in parsed.soft_preferences if p.weight_source != 'companion' and p.derived_from is None]
    return list(dict.fromkeys(keys))


def _ensure_preference(result: ParsedHotelQuery, key: str, desired) -> bool:
    if any(p.feature_key == key for p in result.soft_preferences) or any(h.feature_key == key for h in result.hard_constraints):
        return True
    if len(result.soft_preferences) >= MAX_PREFERENCES:
        return False
    definition = get_registry().get(key)
    result.soft_preferences.append(SoftPreference(feature_key=key, desired=desired, scope=definition.scope,
                                                  weight_source='default'))
    return True


def complete_needs(parsed: ParsedHotelQuery) -> ParsedHotelQuery:
    """Каждое условие и каждая непроверяемая тема — в какой-то потребности."""
    registry = get_registry()
    result = parsed.model_copy(deep=True)
    needs: list[Need] = []
    for need in result.needs:
        if need.kind == 'feature':
            # LLM назвала признак, но не добавила условие — добавляем мягкое по реестру.
            present = set(_primary_keys(result))
            kept = []
            for key in need.features:
                desired = registry.get(key).query_desired
                if key in present or (desired is not None and _ensure_preference(result, key, desired)):
                    kept.append(key)
            if not kept:
                need = Need(quote=need.quote, kind='unsupported', topic=need.quote)
            else:
                need.features = kept
        if need.kind == 'unsupported' and need.topic not in result.unsupported:
            result.unsupported.append(need.topic)
        if not any(n.quote == need.quote and n.kind == need.kind for n in needs):
            needs.append(need)
    covered = {k for n in needs for k in n.features}
    for need in needs:
        if need.kind == 'any_of':
            covered |= {o.feature_key for o in get_concept(need.concept).options}
    for key in _primary_keys(result):
        if key not in covered:
            needs.append(Need(quote=registry.get(key).label.lower(), kind='feature', features=[key]))
            covered.add(key)
    topics = {n.topic for n in needs if n.kind == 'unsupported'}
    for topic in result.unsupported:
        if topic not in topics:
            needs.append(Need(quote=topic, kind='unsupported', topic=topic))
            topics.add(topic)
    result.needs = needs
    return result


def resolve_concepts(parsed: ParsedHotelQuery, choices: dict[str, str] | None = None) -> ParsedHotelQuery:
    """«Вид из окна» → мягкие пожелания по всем вариантам, либо по выбранному гостем."""
    choices = choices or {}
    result = parsed.model_copy(deep=True)
    concepts_in_query = {n.concept for n in result.needs if n.kind == 'any_of'}
    unknown = set(choices) - concepts_in_query
    if unknown:
        raise ValueError(f'В запросе нет пожелания для уточнения: {", ".join(sorted(unknown))}')
    for need in result.needs:
        if need.kind != 'any_of':
            continue
        concept = get_concept(need.concept)
        need.options = [NeedOption(key=o.key, label=o.label, feature_key=o.feature_key) for o in concept.options]
        need.question = concept.question
        chosen = choices.get(need.concept, need.chosen)
        if chosen is not None and chosen != 'any':
            concept.option(chosen)  # неизвестный вариант → ValueError (422)
        need.chosen = chosen if chosen != 'any' else None
        selected = [concept.option(need.chosen)] if need.chosen else concept.options
        # Варианты, от которых гость отказался, убираем, если о них не просили отдельно.
        others = {o.feature_key for o in concept.options} - {o.feature_key for o in selected}
        elsewhere = {k for n in result.needs if n is not need for k in n.features}
        result.soft_preferences = [p for p in result.soft_preferences
                                   if p.feature_key not in others or p.feature_key in elsewhere]
        need.features = [o.feature_key for o in selected if _ensure_preference(result, o.feature_key, o.desired)]
    return result


def prepare(parsed: ParsedHotelQuery, choices: dict[str, str] | None = None) -> ParsedHotelQuery:
    """Полная подготовка запроса к поиску: разметка потребностей + понятия + уточнения."""
    return resolve_concepts(complete_needs(parsed), choices)


def any_of_groups(parsed: ParsedHotelQuery) -> dict[str, set[str]]:
    """Группы «любой из» для ранжирования: понятие → признаки-варианты (если их больше одного)."""
    return {n.concept: set(n.features) for n in parsed.needs
            if n.kind == 'any_of' and n.concept and len(n.features) > 1}
