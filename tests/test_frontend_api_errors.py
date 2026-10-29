import httpx
import pytest
from frontend.api_client import APIClient, APIError


@pytest.mark.parametrize(('status', 'payload', 'code', 'message'), [
    (409, {'code': 'state_conflict', 'detail': 'Решение уже принято'}, 'state_conflict', 'Решение уже принято'),
    (422, {'code': 'invalid_request', 'detail': [{'loc': ['body', 'accept'], 'msg': 'Нужно boolean'}]}, 'invalid_request', 'accept: Нужно boolean'),
    (503, {'detail': 'Сервис недоступен'}, None, 'Сервис недоступен'),
    (500, ['unexpected', 'upstream'], None, 'unexpected'),
])
def test_client_preserves_machine_code_and_supports_legacy_error_body(monkeypatch, status, payload, code, message):
    response = httpx.Response(status, json=payload, request=httpx.Request('GET', 'http://test/api'))
    monkeypatch.setattr(httpx, 'request', lambda *args, **kwargs: response)
    with pytest.raises(APIError) as exc:
        APIClient().get('/api/test')
    assert isinstance(exc.value, RuntimeError)
    assert exc.value.status_code == status and exc.value.code == code
    assert message in str(exc.value)
