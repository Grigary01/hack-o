"""HTTP-адаптеры ML. Клиенты можно подменить MockTransport, БД здесь нет.

Один запрос с timeout, без скрытого fallback и бесконечного retry.
Успешный mock не доказывает качество настоящей модели.
"""
from contextlib import nullcontext
import httpx
from pydantic import ValidationError
from app.core.config import settings
from app.core.errors import ReplyParserUnavailable, ReplyParserContractError
from app.ml.reply_prompts import reply_messages, reply_schema
from app.schemas.hotelier import ReplyExtraction


class HTTPReplyParser:
    def __init__(self, config=settings, client=None):
        self.config = config
        self.client = client

    def post(self, url, payload, headers=None):
        context = nullcontext(self.client) if self.client is not None else httpx.Client(
            timeout=httpx.Timeout(self.config.parser_timeout_seconds, connect=5))
        try:
            with context as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise ReplyParserUnavailable('Сервис разбора ответа недоступен по сети; факты не сохранены.') from exc
        if response.status_code in (401, 403, 404, 408, 429) or response.status_code >= 500:
            raise ReplyParserUnavailable(f'Сервис разбора ответа HTTP {response.status_code}: проверьте настройку, модель и квоту.')
        if not response.is_success:
            raise ReplyParserContractError(f'Сервис разбора ответа отклонил контракт (HTTP {response.status_code}).')
        return response


class OllamaReplyParser(HTTPReplyParser):
    mode = 'ollama'

    def parse(self, *, feature_key, text):
        payload = {'model': self.config.model_name, 'stream': False,
                   'format': reply_schema(feature_key, self.mode),
                   'messages': reply_messages(feature_key, text),
                   'options': {'temperature': self.config.temperature,
                               'num_predict': self.config.max_output_tokens,
                               'num_ctx': self.config.ollama_num_ctx}}
        if self.config.ollama_think is not None:
            payload['think'] = self.config.ollama_think
        response = self.post(self.config.ollama_url.rstrip('/') + '/api/chat', payload)
        try:
            data = response.json()
            if data.get('done') is not True or data.get('done_reason') not in (None, 'stop'):
                raise ValueError('Незавершённый ответ')
            return ReplyExtraction.model_validate_json(data['message']['content'])
        except (ValidationError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ReplyParserContractError('Ollama вернула незавершённый или невалидный разбор ответа.') from exc


class GroqReplyParser(HTTPReplyParser):
    mode = 'groq'

    def parse(self, *, feature_key, text):
        if not self.config.groq_api_key:
            raise ReplyParserUnavailable('Настройте GROQ_API_KEY на backend; обработчик ответа не подключён.')
        payload = {'model': self.config.groq_model,
                   'messages': reply_messages(feature_key, text), 'temperature': self.config.temperature,
                   'max_completion_tokens': self.config.max_output_tokens,
                   'reasoning_effort': self.config.groq_reasoning_effort,
                   'response_format': {'type': 'json_schema', 'json_schema': {
                       'name': 'hotelier_reply', 'strict': False, 'schema': reply_schema(feature_key, self.mode)}}}
        response = self.post(self.config.cloud_base_url + '/chat/completions', payload,
                             headers={'Authorization': 'Bearer ' + self.config.groq_api_key})
        try:
            choice = response.json()['choices'][0]
            if choice.get('finish_reason') != 'stop':
                raise ValueError('Незавершённый ответ')
            return ReplyExtraction.model_validate_json(choice['message']['content'])
        except (ValidationError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
            raise ReplyParserContractError('Groq вернул незавершённый или невалидный разбор ответа.') from exc
