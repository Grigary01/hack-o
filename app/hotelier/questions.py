"""Жизненный цикл одного вопроса на hotel/feature поверх общей истории фактов.

Очередь локального кабинета учитывает симуляцию; флаг гостевого поиска
не превращает уже обработанный демо-ответ в новое уточнение.
"""
from app.features.service import resolve_feature
from app.schemas.hotelier import QuestionContext, ReplyExtraction
from app.storage import repository as storage


def refresh_question(repo, question, *, review_answer=None):
    context = QuestionContext.model_validate(question.context)
    targets = set(context.subject_ids)
    if review_answer is not None:
        if review_answer.question_id != question.id:
            raise ValueError('Ответ не принадлежит вопросу')
        context.review_answer_id = review_answer.id
        extraction = ReplyExtraction.model_validate(review_answer.extraction)
        targets.update(f'{question.hotel_id}:room:{c.room_number}' for c in extraction.claims)

    observations = repo.observations(question.hotel_id, question.feature_key)
    targets.update(o.subject_id for o in observations)
    conflicts = repo.conflict_records(question.hotel_id)
    now = storage.now_utc()
    reasons, pending_subjects = set(), set()
    for subject_id in targets:
        state = resolve_feature(observations, subject_id, question.feature_key,
                                include_simulated=True, now=now, conflicts=conflicts)
        if state.value is None:
            reasons.add(state.status)
            pending_subjects.add(subject_id)
    if not targets:
        reasons.add('unknown')

    # Фокус на последнем отправленном разборе хранится явно: одинаковые даты
    # и порядок UUID не определяют, какой ответ был последним. Старые черновики
    # остаются в истории, но не отменяют более поздний подтверждённый ответ.
    if context.review_answer_id is not None:
        answer = repo.answer(context.review_answer_id)
        if answer.question_id != question.id:
            raise ValueError('Контекст содержит ответ другого вопроса')
        if answer.status in ('pending', 'rejected'):
            extraction = ReplyExtraction.model_validate(answer.extraction)
            pending_subjects.update(f'{question.hotel_id}:room:{c.room_number}' for c in extraction.claims)
        if answer.status == 'pending':
            reasons.add('pending_answer')
            if extraction.unparsed:
                reasons.add('unparsed_answer')
        elif answer.status == 'rejected':
            reasons.add('rejected_answer')

    new_context = QuestionContext(reasons=sorted(reasons), subject_ids=sorted(pending_subjects),
                                  review_answer_id=context.review_answer_id).model_dump()
    status = 'open' if reasons else 'answered'
    if question.status != status or question.context != new_context:
        question.status = status
        question.context = new_context
        question.updated_at = now.isoformat()
        repo.session.flush()
    return question
