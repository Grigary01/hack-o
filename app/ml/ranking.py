"""Прозрачный подбор по фактам: строгая фильтрация + мягкое ранжирование.

Хотя файл находится в ml/, в MVP это НЕ обученная модель ранжирования.
Здесь обычная детерминированная математика: одинаковые факты и запрос
дают одинаковый результат. LLM не назначает score и не решает, где есть море.

Формула близости адаптирована из POISearchDemo.score_pois_by_proximity
(Maxim, MIT). Исправлены нулевое расстояние, unknown и разделение hard/soft.
"""
import operator
from collections.abc import Sequence
from app.schemas.conflicts import Conflict

from app.features.registry import get_registry
from app.features.service import resolve_feature
from app.features.cross_check import model_disagreements
from app.schemas.hotel import Hotel, Observation
from app.schemas.query import ParsedHotelQuery, SoftPreference
from app.schemas.search import CriterionResult, HotelSearchResult
from app.ml.multicriteria import curve_match, aggregate, mark_dominated

# Whitelist математических операций. Например, OPS['<='](319.8, 500) → True.
# eval строк пользователя/модели здесь не нужен и не используется.
OPS = {
    '<': operator.lt,
    '<=': operator.le,
    '=': operator.eq,
    '>=': operator.ge,
    '>': operator.gt,
    '!=': operator.ne,
}


def soft_match(value, preference: SoftPreference) -> float:
    """Переводит ОДНО известное свойство в соответствие от 0 до 1.

    Для близости: distance=0 → 1; distance=scale → .5. scale=1000 означает
    «характерный масштаб 1 км», а не строгий порог. При желании far всё наоборот.
    Для упорядоченных категорий (ordinal в реестре) соседние значения частично
    совпадают: 1 - |позиция value - позиция desired| / (число вариантов - 1).
    Тишина high: high → 1, medium → .5, low → 0; вид wide: partial → .5.
    Для bool: True/False сравниваются с желанием, включая desired=False.

    None сюда не передаётся: неизвестное обрабатывается до вызова функции.
    """
    if preference.utility is not None:
        return curve_match(value, preference.utility)
    definition = get_registry().get(preference.feature_key)
    if definition.type == 'number' and preference.desired in ('near', 'far'):
        near = 1 / (1 + value / definition.scale)
        return near if preference.desired == 'near' else 1 - near
    if definition.type == 'category' and definition.ordinal and value in definition.choices:
        distance = abs(definition.choices.index(value) - definition.choices.index(preference.desired))
        return 1 - distance / (len(definition.choices) - 1)
    return float(value == preference.desired)


def describe(definition, state, fallback):
    """Текст для гостя: значение по-русски + объяснение источника.

    Расчётные характеристики кладут в evidence.details.explanation конкретику:
    сторону, этаж, месяцы, расстояние до траектории. Её и показываем вместо
    общего описания — так видно, в чём отель не дотягивает («только с 5-го этажа»).
    """
    if state.value is None:
        return f'{definition.label}: {fallback}. {definition.description}'
    newest = max((o for o in state.observations if o.value == state.value), key=lambda o: o.collected_at)
    detail = newest.evidence.details.get('explanation') if isinstance(newest.evidence.details, dict) else None
    value = definition.display(state.value)
    if definition.unit == 'm' and isinstance(state.value, (int, float)):
        value = f'≈ {round(state.value / 10) * 10:.0f} м'
    confidence = {'medium': 'средняя', 'low': 'низкая', 'high': 'высокая'}.get(newest.confidence_level)
    text = f'{definition.label}: {value}. {detail or definition.description}'
    return text + (f' Уверенность: {confidence}.' if confidence and detail else '')


def rank_variant(
    hotel: Hotel,
    room_id: str | None,
    observations: list[Observation],
    parsed: ParsedHotelQuery,
    include_simulated: bool,
    ranking_method: str = 'weighted_v1',
    balance: float = .25,
    *, conflicts: Sequence[Conflict] = (),
) -> HotelSearchResult:
    """Оценивает одну комбинацию «отель + конкретный номер».

    Если номер неизвестен, room_id=None: room-факты станут unknown.
    resolve_feature занимается датами/конфликтами/симуляцией; ranker получает
    только разрешённое текущее значение. История прикладывается к объяснению.
    """
    criteria = []  # Подробные объяснения по каждому условию для frontend.
    outcomes = []  # True / False / None для строгих условий.
    total_weight = 0.  # Все активные мягкие пожелания, включая неизвестные.
    known_weight = 0.  # Только пожелания, для которых известны факты.
    score_sum = 0.  # Сумма weight × match по известным фактам.
    matches = {}

    # Блок A. Строгие условия НЕ входят в среднюю оценку.
    # Нарушение «не дальше 500 м» нельзя компенсировать хорошим видом.
    for hard in parsed.hard_constraints:
        subject = hotel.id if hard.scope == 'hotel' else room_id
        state = resolve_feature(observations, subject, hard.feature_key, include_simulated, conflicts=conflicts)

        # Важно именно `is None`, не `if not state.value`:
        # 0 метров и False («нет вида») — полноценные известные значения.
        result = None if state.value is None else OPS[hard.operator](state.value, hard.value)
        outcome = 'unknown' if result is None else 'matched' if result else 'violated'
        outcomes.append(result)
        definition = get_registry().get(hard.feature_key)
        model_reviews = model_disagreements(observations, hotel.id, subject, hard.feature_key, include_simulated, conflicts=conflicts) \
            if hard.scope == 'room' else []
        explanation = describe(definition, state, 'нет надёжных данных') + \
            f' Условие: {hard.operator} {definition.display(hard.value)} {hard.unit or ""}.'.rstrip()
        criteria.append(CriterionResult(
            feature_key=hard.feature_key,
            requested=f'{hard.operator} {hard.value}',
            actual=state.value,
            outcome=outcome,
            status=state.status,
            subject_id=subject,
            explanation=explanation + ''.join(' ⚠ ' + c['text'] for c in model_reviews),
            evidence=state.observations,
            model_conflicts=model_reviews,
        ))

    # Блок B. Мягкие пожелания задают порядок среди кандидатов.
    # Нулевой вес означает «не учитывать» — убираем и из числителя, и из знаменателя.
    for preference in parsed.soft_preferences:
        if preference.importance == 0:
            continue
        subject = hotel.id if preference.scope == 'hotel' else room_id
        state = resolve_feature(observations, subject, preference.feature_key, include_simulated, conflicts=conflicts)
        total_weight += preference.importance
        match = None if state.value is None else soft_match(state.value, preference)
        matches[preference.feature_key] = match
        if match is not None:
            known_weight += preference.importance
            score_sum += preference.importance * match

        definition = get_registry().get(preference.feature_key)
        model_reviews = model_disagreements(observations, hotel.id, subject, preference.feature_key, include_simulated, conflicts=conflicts) \
            if preference.scope == 'room' else []
        explanation = describe(definition, state, 'требует уточнения')
        if preference.derived_from:
            explanation += f' (добавлено к пожеланию «{get_registry().get(preference.derived_from).label.lower()}»)'
        criteria.append(CriterionResult(
            feature_key=preference.feature_key,
            requested=str(preference.utility.model_dump(exclude_none=True)) if preference.utility else str(preference.desired),
            actual=state.value,
            outcome='unknown' if match is None else 'preference',
            status=state.status,
            subject_id=subject,
            match=match,
            explanation=explanation + ''.join(' ⚠ ' + c['text'] for c in model_reviews),
            evidence=state.observations,
            model_conflicts=model_reviews,
        ))

    # Блок C. Считаем две отдельные величины; score без coverage вводил бы в заблуждение.
    # Пример: тишина high (вес .9), вид неизвестен (вес .6).
    # score = .9*1/.9 = 1; coverage = .9/(.9+.6) = .6; ranking_score = .6.
    # Это НЕ «идеальный отель», а совпадение известных 60% мягких пожеланий.
    coverage = known_weight / total_weight if total_weight else 0.
    score = score_sum / known_weight if known_weight else None

    # Любое False сильнее неизвестности. Нет False, но есть None → нужно уточнение.
    # Пустой список строгих условий означает отсутствие запретов, поэтому True.
    eligible = False if False in outcomes else None if None in outcomes else True
    warnings = []
    if any(criterion.status == 'estimated' for criterion in criteria):
        warnings.append('Часть условий оценена по расчёту и на месте не проверялась.')
    if any(criterion.model_conflicts for criterion in criteria):
        warnings.append('Ответ отеля расходится с расчётом по зданию — нужна перепроверка.')
    if any(
        observation.evidence.source.type == 'hotelier_simulated'
        for criterion in criteria
        for observation in criterion.evidence
    ):
        warnings.append('Учтены тестовые ответы отеля: в текущей версии это пример, а не подтверждённые свойства отеля.')

    # uncertainty здесь — 1 - coverage мягких пожеланий, НЕ вероятность ошибки.
    # Числовая сортировочная оценка 0 допустима, даже если отображаемый score=None.
    interval = None
    group_scores = []
    ranking_score = (score or 0)*coverage
    if ranking_method == 'balanced_v2':
        # Группировка и слабая группа влияют только на ранжирование; hard result
        # не меняется. Интервал отражает отсутствие фактов, не вероятность.
        summary = aggregate(parsed.soft_preferences,matches,balance)
        coverage,score = summary['coverage'],summary['score']
        ranking_score = summary['lower']
        interval = (round(summary['lower'],4),round(summary['upper'],4))
        group_scores = summary['groups']
    return HotelSearchResult(
        hotel=hotel,
        eligible=eligible,
        recommended_room_id=room_id,
        score=round(score, 4) if score is not None else None,
        coverage=round(coverage, 4),
        ranking_score=round(ranking_score, 4),
        uncertainty=round(1 - coverage, 4),
        criteria=criteria,
        warnings=warnings,
        ranking_method=ranking_method,ranking_interval=interval,group_scores=group_scores,
    )


def rank_hotels(
    parsed: ParsedHotelQuery,
    hotels_and_facts: list[tuple[Hotel, list[Observation]]],
    include_simulated: bool = False,
    ranking_method: str = 'weighted_v1',
    balance: float = .25,
    *, conflicts: Sequence[Conflict] = (),
) -> dict[str, list[HotelSearchResult]]:
    """Для каждого отеля выбирает лучший допустимый номер и распределяет по группам.

    Нельзя собрать «идеальный номер» из разных комнат: вид в 301 +
    шумоизоляция в 302 не удовлетворяют двум требованиям к одному номеру.
    Поэтому сначала rank_variant для каждой комнаты, потом выбор варианта.
    """
    if ranking_method not in ('weighted_v1','balanced_v2') or not 0 <= balance <= 1:
        raise ValueError('Некорректная политика ранжирования')
    groups = {'matched': [], 'needs_verification': [], 'excluded': []}
    room_requested = any(
        requirement.scope == 'room'
        for requirement in parsed.hard_constraints + parsed.soft_preferences
    )

    for hotel, observations in hotels_and_facts:
        # Для обычного поиска даже список комнат не берём из симуляции.
        rooms = sorted({
            observation.subject_id
            for observation in observations
            if observation.subject_type == 'room'
            and (include_simulated or observation.evidence.source.type != 'hotelier_simulated')
        })
        candidate_room_ids = (rooms or [None]) if room_requested else [None]
        variants = [
            rank_variant(hotel, room_id, observations, parsed, include_simulated, ranking_method, balance,
                         conflicts=conflicts)
            for room_id in candidate_room_ids
        ]

        # Сначала соответствие строгим условиям, затем мягкая оценка и coverage.
        # Кортеж сравнивается слева направо: прекрасный score не спасает hard violation.
        result = max(variants, key=lambda variant: (
            {True: 2, None: 1, False: 0}[variant.eligible],
            variant.ranking_score,
            variant.coverage,
        ))
        hotel_violated = any(
            criterion.outcome == 'violated' and criterion.subject_id == hotel.id
            for criterion in result.criteria
        )
        if result.eligible is False and not hotel_violated:
            # В БД нет полного каталога номеров. Если ВСЕ ИЗВЕСТНЫЕ номера не
            # подходят, остаётся возможность неизвестного подходящего номера.
            # Отель отправляется на уточнение, не объявляется целиком неподходящим.
            result.eligible = None
            result.recommended_room_id = None
            result.warnings.append('В известных номерах совместного соответствия нет; полный список номеров неизвестен.')

        if result.eligible is True:
            group = 'matched'
        elif result.eligible is False:
            group = 'excluded'
        else:
            group = 'needs_verification'
        groups[group].append(result)

    # Минус в ключе означает убывание. ID — стабильный tie-breaker:
    # при равенстве оценок карточки не прыгают между запросами.
    for candidates in groups.values():
        candidates.sort(key=lambda item: (-item.ranking_score, -item.coverage, item.hotel.id))
        if ranking_method == 'balanced_v2':
            mark_dominated(candidates)
    return groups
