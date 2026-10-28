"""HTTP-контракт для очереди; существующий APIClient можно заменить заглушкой."""
from urllib.parse import quote, urlencode
from frontend.api_client import APIClient


class QuestionClient:
    def __init__(self, api=None):
        self.api = api if api is not None else APIClient()

    def list_questions(self, hotel_id=None, status=None):
        query = {key: value for key, value in {'hotel_id': hotel_id, 'status': status}.items()
                 if value is not None}
        return self.api.get('/api/hotelier/questions' + ('?' + urlencode(query) if query else ''))

    def create_question(self, hotel_id, feature_key):
        return self.api.post('/api/hotelier/questions', {'hotel_id': hotel_id, 'feature_key': feature_key})

    def submit_answer(self, question_id, text):
        path = '/api/hotelier/questions/' + quote(question_id, safe='') + '/answer'
        return self.api.post(path, {'text': text})

    def confirm_answer(self, answer_id, accept):
        path = '/api/hotelier/answers/' + quote(answer_id, safe='') + '/confirm'
        return self.api.post(path, {'accept': accept})

    def get_answer(self, answer_id):
        return self.api.get('/api/hotelier/answers/' + quote(answer_id, safe=''))
