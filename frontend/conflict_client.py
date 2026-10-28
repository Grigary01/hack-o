"""Клиент экрана конфликтов; frontend знает только HTTP.

Настоящий клиент: ConflictClient(). Для автономной разработки экрана:
ConflictClient(api=StubConflictAPI()). Заглушка никогда не включается автоматически.
"""
from urllib.parse import quote, urlencode
from frontend.api_client import APIClient


class ConflictClient:
    def __init__(self, api=None):
        self.api = api if api is not None else APIClient()

    def list_conflicts(self, hotel_id=None, status=None):
        query = {k: v for k, v in {'hotel_id': hotel_id, 'status': status}.items() if v is not None}
        path = '/api/hotelier/conflicts'
        return self.api.get(path + ('?' + urlencode(query) if query else ''))

    def resolve_conflict(self, conflict_id, selected_observation_id, reason):
        path = '/api/hotelier/conflicts/' + quote(conflict_id, safe='') + '/resolve'
        return self.api.post(path, {'selected_observation_id': selected_observation_id, 'reason': reason})
