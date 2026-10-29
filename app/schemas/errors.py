"""Единая форма обработанных ошибок; detail совместим с прежним API."""
from typing import Any, Literal
from app.schemas.query import Contract


class APIError(Contract):
    code: Literal['not_found', 'invalid_request', 'state_conflict', 'service_unavailable',
                  'invalid_model_output', 'forbidden', 'http_error']
    detail: str | list[dict[str, Any]] | dict[str, Any]


ERROR_RESPONSES = {status: {'model': APIError} for status in (403, 404, 409, 422, 502, 503)}
