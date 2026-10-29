class StateConflictError(ValueError):
    """Корректное действие несовместимо с уже сохранённым решением (HTTP 409)."""


class NotFoundError(LookupError):
    """Отсутствует доменный объект; не маскирует случайный KeyError как 404."""


class ReplyParserError(Exception):
    """Ошибка обработчика ответа; не заменяется выдуманными фактами."""


class ReplyParserUnavailable(ReplyParserError):
    """Модель/ключ/сервис недоступны (HTTP 503)."""


class ReplyParserContractError(ReplyParserError):
    """Обработчик вернул неподходящую структуру или свидетельство (HTTP 502)."""
