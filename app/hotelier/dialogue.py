"""Диалог: заменяемый разбор -> проверенный pending -> подтверждение -> наблюдения.

parse_hotelier_reply сохранён как совместимый импорт старого bounded parser.
Все ответы локального кабинета остаются симуляцией, включая подтверждённые.
"""
import uuid
from datetime import timedelta
from sqlalchemy import update
from app.features.registry import get_registry
from app.schemas.hotelier import ReplyExtraction
from app.schemas.hotel import Observation, Evidence, Source
from app.storage.models import RoomRow, AnswerRow
from app.storage.repository import now_utc, row_dict
from app.hotelier.rule_reply_parser import parse_hotelier_reply
from app.hotelier.reply_parser import BoundedRuleReplyParser
from app.hotelier.reply_validation import validate_reply_extraction, parse_reply
from app.core.errors import ReplyParserContractError, StateConflictError


def ask_hotelier(repo,hotel_id,feature_key):
    definition = get_registry().get(feature_key)
    if definition.provider != 'hotelier':
        raise ValueError('Для этой характеристики нужен Geo-инструмент')
    return row_dict(repo.ensure_question(hotel_id,feature_key,definition.question))


def submit_answer(repo,qid,text,*,reply_parser=None):
    # Pending сохраняет текст и предложенный разбор, но ещё НЕ создаёт факты.
    question = repo.question(qid)
    if not text.strip():
        raise ValueError('Ответ не должен быть пустым')
    extraction = parse_reply(reply_parser if reply_parser is not None else BoundedRuleReplyParser(),
                             feature_key=question.feature_key, text=text)
    row = AnswerRow(id=uuid.uuid4().hex,question_id=qid,text=text,
        extraction=extraction.model_dump(mode='json'),status='pending',simulated=True,created_at=now_utc().isoformat())
    repo.session.add(row)
    repo.session.flush()
    from app.hotelier.questions import refresh_question
    refresh_question(repo, question, review_answer=row)
    return row_dict(row)


def confirmation_result(repo, answer, *, idempotent=False):
    question = repo.question(answer.question_id)
    repo.refresh_existing_question(question.hotel_id, question.feature_key)
    accepted = answer.status == 'confirmed'
    ids = sorted(o.id for o in repo.observations(question.hotel_id)
                 if accepted and o.evidence.source.ref == answer.id
                 and o.evidence.source.type == 'hotelier_simulated')
    return {'answer_id': answer.id, 'status': answer.status, 'idempotent': idempotent,
            'observation_ids': ids, 'conflicts': repo.conflicts(question.hotel_id) if accepted else [],
            'source_type': 'hotelier_simulated' if accepted else None, 'question': row_dict(question)}


def confirm_answer(repo,answer_id,accept):
    """Применяет решение человека в транзакции, которую открыл API dependency.

    Confirmation подтверждает корректность разбора учебного текста, не факт
    реального осмотра гостиницы. Поэтому источник остаётся simulated/estimated.
    """
    answer = repo.answer(answer_id)
    target = 'confirmed' if accept else 'rejected'
    if answer.status == target:
        return confirmation_result(repo, answer, idempotent=True)
    if answer.status != 'pending':
        raise StateConflictError('Решение уже принято; создайте новый ответ')
    question = repo.question(answer.question_id)
    if accept:
        try:
            extraction = validate_reply_extraction(answer.extraction,
                feature_key=question.feature_key, text=answer.text)
        except ReplyParserContractError as exc:
            raise ValueError('Сохранённый разбор не соответствует вопросу или исходному тексту.') from exc
    else:
        extraction = ReplyExtraction.model_validate(answer.extraction)
    if accept and (not extraction.claims or extraction.unparsed):
        raise ValueError('Ответ разобран не полностью. Отклоните его и уточните формулировку.')
    # Атомарный переход защищает повторные/concurrent подтверждения.
    changed = repo.session.execute(update(AnswerRow).where(AnswerRow.id==answer_id,AnswerRow.status=='pending').values(status=target))
    if changed.rowcount != 1:
        raise StateConflictError('Ответ уже обработан другим запросом')
    question = repo.question(answer.question_id)
    if not accept:
        return confirmation_result(repo, answer)
    now = now_utc()
    for claim in extraction.claims:
        room_id = f'{question.hotel_id}:room:{claim.room_number}'
        room = repo.session.get(RoomRow,room_id)
        if room is None:
            repo.session.add(RoomRow(id=room_id,hotel_id=question.hotel_id,number=claim.room_number,floor=claim.floor))
        elif claim.floor is not None and room.floor is None:
            room.floor = claim.floor
        definition = get_registry().get(claim.feature_key)
        observation = Observation(id=f'{answer_id}:{claim.room_number}',hotel_id=question.hotel_id,
            subject_type='room',subject_id=room_id,feature_key=claim.feature_key,value=claim.value,
            observed_at=now,collected_at=now,expires_at=now+timedelta(days=definition.ttl_days),
            status='estimated',confidence_level='low',confidence_method='Подтверждён разбор симуляции, не истинность свойства.',
            quality_flags=['simulated','hotelier_claim_not_independently_verified'],
            evidence=Evidence(source=Source(type='hotelier_simulated',name='Отельер (демо)',ref=answer_id),
                method='human_confirmed_extraction',raw_excerpt=answer.text,
                details={'quote':claim.quote,'floor':claim.floor,'question_id':question.id}))
        repo.save_observation(observation)
    repo.refresh_existing_question(question.hotel_id, question.feature_key)
    repo.session.flush()
    return confirmation_result(repo, answer)
