"""Проверка недоверенного результата ML перед pending и повторно перед записью фактов."""
import re
import httpx
from pydantic import ValidationError
from app.core.errors import ReplyParserContractError, ReplyParserUnavailable
from app.features.registry import get_registry
from app.schemas.hotelier import ReplyExtraction

# В схеме нет сезонности/условий. Это консервативный барьер известных оговорок,
# а не проверка истинности свободного текста: разбор по-прежнему проверяет человек.
UNSUPPORTED_CONTEXT = re.compile(
    r'\b(?:если|когда|пока|кроме|только|услови\w*|завис\w*|частично|иногда|возможно|наверно|наверное|кажется|не\s+уверен[аы]?|'
    r'планиру\w*|будет|будут|летом|зимой|весной|осенью|утром|вечером|ночью|дн[её]м|'
    r'сезон\w*|январ\w*|феврал\w*|март\w*|апрел\w*|ма[йея]|июн\w*|июл\w*|'
    r'август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)\b', re.I)


def room_is_cited(number, quote):
    if re.search(r'(?<!\d)' + re.escape(number) + r'(?!\d)', quote):
        return True
    return any(int(start) <= int(number) <= int(end) for start, end in
               re.findall(r'(?<!\d)(\d{1,5})\s*[-–—]\s*(\d{1,5})(?!\d)', quote))


def validate_reply_extraction(raw, *, feature_key, text, parser_mode=None):
    definition = get_registry().get(feature_key)
    if definition.provider != 'hotelier' or definition.scope != 'room' or definition.type != 'boolean':
        raise ValueError('Для этой характеристики не поддерживается ответ отельера')
    try:
        # model_validate(instance) без этого шага может пропустить мутацию
        # вложенных объектов или результат model_construct() внешнего parser.
        data = raw.model_dump(mode='python', warnings=False) if isinstance(raw, ReplyExtraction) else raw
        result = ReplyExtraction.model_validate(data)
        if parser_mode is not None:
            if not isinstance(parser_mode, str) or not parser_mode.strip():
                raise ValueError('Неверный режим обработчика')
            result.parser_mode = parser_mode
        by_room, unique, issues = {}, [], [s for s in result.unparsed if s.strip()]
        for claim in result.claims:
            if claim.feature_key != feature_key:
                raise ValueError('Характеристика ответа не соответствует вопросу')
            get_registry().validate_value(feature_key, claim.value)
            if not claim.quote.strip() or claim.quote not in text:
                raise ValueError('Цитата должна дословно присутствовать в исходном ответе')
            if not room_is_cited(claim.room_number, claim.quote):
                raise ValueError('Цитата не содержит указанного номера или диапазона')
            old = by_room.get(claim.room_number)
            if old is not None:
                if old.value != claim.value or (old.floor is not None and claim.floor is not None
                                               and old.floor != claim.floor):
                    issues.append(f'Противоречие внутри ответа о номере {claim.room_number}')
                    unique.append(claim)
                elif old.floor is None and claim.floor is not None:
                    unique[unique.index(old)] = claim
                    by_room[claim.room_number] = claim
            else:
                unique.append(claim)
                by_room[claim.room_number] = claim
        if result.claims and UNSUPPORTED_CONTEXT.search(text):
            issues.append('Ответ содержит условие, сезонность или неопределённость; требуется уточнение: ' + text)
        if not unique and not issues:
            issues.append('Не получены конкретные утверждения; уточните номера и свойство.')
        result.claims = unique
        result.unparsed = list(dict.fromkeys(issues))
        return result
    except (ValidationError, ValueError, TypeError) as exc:
        raise ReplyParserContractError('Обработчик ответа вернул невалидный разбор; факты не сохранены.') from exc


def parse_reply(parser, *, feature_key, text):
    # Проверяем вопрос до внешнего вызова. Идентификаторы отеля/вопроса в ML не уходят.
    if get_registry().get(feature_key).provider != 'hotelier':
        raise ValueError('Для этой характеристики нужен Geo-инструмент')
    try:
        raw = parser.parse(feature_key=feature_key, text=text)
    except (TimeoutError, OSError, httpx.HTTPError) as exc:
        raise ReplyParserUnavailable('Обработчик ответа недоступен; повторите позже. Факты не сохранены.') from exc
    except (ValidationError, ValueError, TypeError) as exc:
        raise ReplyParserContractError('Обработчик ответа вернул невалидный разбор; факты не сохранены.') from exc
    mode = getattr(parser, 'mode', 'injected')
    if not isinstance(mode, str) or not mode.strip():
        raise ReplyParserContractError('Обработчик ответа не указал корректный режим.')
    return validate_reply_extraction(raw, feature_key=feature_key, text=text, parser_mode=mode)
