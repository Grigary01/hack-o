"""Сохранённый bounded offline-разбор. Не зависит от БД и HTTP."""
import re
from app.features.registry import get_registry
from app.schemas.hotelier import RoomClaim, ReplyExtraction

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
    # «…201–203 есть вид на море, в 101 нет» — запятая перед «а/но/в/у» тоже граница:
    # иначе «нет» из второй части приписывалось номерам 201–203.
    for clause in re.split(r'[;.!?\n]+|,\s*(?=(?:а|но|в|во|у)\s)', text, flags=re.I):
        if not clause.strip():
            continue
        normalized = clause.lower().replace('ё','е').replace('вида','вид').replace('шумоизоляции','шумоизоляция')
        matches = list(ROOMS.finditer(clause))
        mentions_feature = any(
            re.search(r'(?<!\w)' + re.escape(alias.lower()) + r'(?!\w)', normalized)
            for alias in definition.aliases
        )
        uncertain = re.search(r'\b(?:возможно|наверно|кажется|если|кроме|но|частично|будет|будут|летом|зимой)\b|\b(?:планиру|апрел|август|июн|июл)',normalized)
        # Номер вне распознанной группы («…есть, а 101 нет» без слова «номер») —
        # значение нельзя честно отнести к группе: отдаём человеку.
        span = matches[0].span() if len(matches) == 1 else (0, 0)
        stray = [m for m in re.finditer(r'(?<![\d-])\d{3,5}(?![\d])', clause) if not span[0] <= m.start() < span[1]]
        if len(matches)!=1 or not mentions_feature or uncertain or stray:
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
