"""Ограниченный offline-парсер свободных ответов; неизвестные конструкции не угадывает.

Текст можно формулировать свободно в простых утвердительных/отрицательных
предложениях о номерах. Сезонность, исключения и сложные условия требуют уточнения.
Все ответы этого локального кабинета — симуляция, включая подтверждённые.
"""
import re
import uuid
from datetime import timedelta
from sqlalchemy import update
from app.features.registry import get_registry
from app.schemas.hotelier import RoomClaim, ReplyExtraction
from app.schemas.hotel import Observation, Evidence, Source
from app.storage.models import RoomRow, AnswerRow
from app.storage.repository import now_utc, row_dict
from app.features.cross_check import model_disagreements

ROOMS = re.compile(r'(?:номер(?:ах|ами|ов|ом|а|е)?|комнат(?:ах|ы|е))\s*№?\s*(\d{1,5}(?:\s*[-–—]\s*\d{1,5})?(?:\s*,\s*\d{1,5})*)',re.I)


def parse_hotelier_reply(feature_key, text):
    """Извлекает утверждения, но ничего не пишет в БД.

    feature_key приходит из вопроса агента: мы разбираем ответ об ОДНОМ свойстве.
    claims — то, что получилось разобрать; unparsed — то, что требует человека.
    Даже claims нельзя автоматически считать истиной: ниже есть подтверждение.
    """
    definition = get_registry().get(feature_key)
    if definition.provider != 'hotelier':
        raise ValueError('Эта характеристика не поддерживается provider=hotelier')
    result = ReplyExtraction()
    # 1. Разделяем простые предложения. Несколько групп номеров в одном
    # предложении могут иметь разные свойства — такой случай не угадываем.
    for clause in re.split(r'[;.!?\n]+', text):
        if not clause.strip():
            continue
        normalized = clause.lower().replace('ё','е').replace('вида','вид').replace('шумоизоляции','шумоизоляция')
        matches = list(ROOMS.finditer(clause))
        mentions_feature = any(alias.lower() in normalized for alias in definition.aliases)
        uncertain = re.search(r'\b(?:возможно|наверно|кажется|если|кроме|но|частично|будет|будут|летом|зимой)\b|\b(?:планиру|апрел|август|июн|июл)',normalized)
        if len(matches)!=1 or not mentions_feature or uncertain:
            result.unparsed.append(clause.strip())
            continue
        numbers = []
        # 2. «301–305» разворачивается в пять отдельных room claims.
        # Обратный/слишком большой диапазон отклоняется, чтобы не породить
        # тысячи фиктивных номеров из опечатки.
        for part in matches[0][1].split(','):
            ends = re.split(r'[-–—]',part)
            first,last = int(ends[0]),int(ends[-1])
            if last < first or last-first > 30:
                numbers=[]
                break
            numbers.extend(str(n) for n in range(first,last+1))
        if not numbers:
            result.unparsed.append(clause.strip())
            continue
        negative = bool(re.search(r'\b(нет|без|отсутствует|отсутствуют|не\s+виден|не\s+видно|не\s+имеет|не\s+имеют)', normalized))
        # 3. False — утверждение об отсутствии, не отсутствие сведений.
        # Неизвестная конструкция с «не» требует переформулировки.
        if 'не ' in normalized and not negative:
            result.unparsed.append(clause.strip())
            continue
        floor = re.search(r'(\d{1,2})\s*[-–]?\s*(?:м|й|ом)?\s*этаж',normalized)
        # 4. Сохраняем исходную цитату рядом с каждым извлечённым значением.
        # Этаж — контекст утверждения, сам по себе он не доказывает вид на море.
        for number in numbers:
            result.claims.append(RoomClaim(room_number=number,floor=int(floor[1]) if floor else None,
                feature_key=feature_key,value=not negative,quote=clause.strip()))
    by_room = {}
    # 5. Нельзя подтвердить ответ, который сам себе противоречит.
    for claim in result.claims:
        if claim.room_number in by_room and by_room[claim.room_number] != claim.value:
            result.unparsed.append(f'Противоречие внутри ответа о номере {claim.room_number}')
        by_room[claim.room_number] = claim.value
    return result


def ask_hotelier(repo,hotel_id,feature_key):
    definition = get_registry().get(feature_key)
    if definition.provider != 'hotelier':
        raise ValueError('Для этой характеристики нужен Geo-инструмент')
    text = definition.question
    check = definition.model_check
    if check:
        # Агент спрашивает предметно: показывает отельеру, что уже посчитал по зданию.
        computed = [o for o in repo.observations(hotel_id, check.potential) if o.value is not None]
        if computed:
            hint = max(computed, key=lambda o: o.collected_at).evidence.details.get('explanation')
            if hint:
                text += ' Наш расчёт по рельефу и соседним домам: ' + hint + ' Подтвердите или поправьте.'
    return row_dict(repo.ensure_question(hotel_id,feature_key,text))


def submit_answer(repo,qid,text):
    # Pending сохраняет текст и предложенный разбор, но ещё НЕ создаёт факты.
    question = repo.question(qid)
    extraction = parse_hotelier_reply(question.feature_key,text)
    row = AnswerRow(id=uuid.uuid4().hex,question_id=qid,text=text,
        extraction=extraction.model_dump(mode='json'),status='pending',simulated=True,created_at=now_utc().isoformat())
    repo.session.add(row)
    repo.session.flush()
    return row_dict(row)


def confirm_answer(repo,answer_id,accept):
    """Применяет решение человека в транзакции, которую открыл API dependency.

    Confirmation подтверждает корректность разбора учебного текста, не факт
    реального осмотра гостиницы. Поэтому источник остаётся simulated/estimated.
    """
    answer = repo.answer(answer_id)
    target = 'confirmed' if accept else 'rejected'
    if answer.status == target:
        return {'answer_id':answer_id,'status':target,'idempotent':True}
    if answer.status != 'pending':
        raise ValueError('Решение уже принято; создайте новый ответ')
    extraction = ReplyExtraction.model_validate(answer.extraction)
    if accept and (not extraction.claims or extraction.unparsed):
        raise ValueError('Ответ разобран не полностью. Отклоните его и уточните формулировку.')
    # Атомарный переход защищает повторные/concurrent подтверждения.
    changed = repo.session.execute(update(AnswerRow).where(AnswerRow.id==answer_id,AnswerRow.status=='pending').values(status=target))
    if changed.rowcount != 1:
        raise ValueError('Ответ уже обработан другим запросом')
    question = repo.question(answer.question_id)
    if not accept:
        return {'answer_id':answer_id,'status':target}
    now = now_utc()
    ids = []
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
        ids.append(repo.save_observation(observation))
    question.status = 'answered'
    repo.session.flush()
    # Сверка с расчётом по зданию: значение отельера остаётся, расхождение помечается.
    observations = repo.observations(question.hotel_id)
    review = []
    for room_id in sorted({f'{question.hotel_id}:room:{c.room_number}' for c in extraction.claims}):
        for item in model_disagreements(observations, question.hotel_id, room_id, question.feature_key,
                                        include_simulated=True):
            repo.add_review_conflict(question.hotel_id, room_id, question.feature_key,
                                     item['hotelier_observation_id'], item['model_observation_id'], item['reason'])
            review.append(item | {'room_id': room_id})
    return {'answer_id':answer_id,'status':target,'observation_ids':ids,'model_review':review,
            'conflicts':repo.conflicts(question.hotel_id),'source_type':'hotelier_simulated'}
