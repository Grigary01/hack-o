"""Понимание пользовательского запроса: русский текст → ParsedHotelQuery.

Здесь мы узнаём, ЧЕГО ХОЧЕТ пользователь. Здесь нет сведений о том,
действительно ли отель тихий или есть ли в его номерах вид на море.

Два взаимозаменяемых провайдера:
* FixtureQueryParser — заранее подготовленные ответы для офлайн-демо.
* OllamaQueryParser — запрос к локальной LLM с проверкой JSON-контракта.

Никакая модель в этом файле не обучается. Мы используем готовую модель
через HTTP. Подробный маршрут чтения кода: docs/ML_GUIDE.md.
"""
import json
import time
from typing import Protocol

import httpx
from pydantic import ValidationError

from app.core.config import ROOT, settings
from app.schemas.query import ParsedHotelQuery
from app.features.registry import get_registry


class ParserError(ValueError):
    """Отличает проблему LLM от обычной ошибки ввода. API вернёт HTTP 502."""


class QueryParser(Protocol):
    """Общий интерфейс, а не третий парсер.

    Protocol означает: любой объект с mode и parse(text) подходит backend.
    Поэтому API не обязан знать, работает сейчас Ollama или офлайн-демо.
    Многоточие ниже — объявление интерфейса, не незавершённая реализация.
    """
    mode: str

    def parse(self, text: str) -> ParsedHotelQuery: ...


def normalize(text: str) -> str:
    """Минимальная нормализация ключа для поиска в словаре fixtures.

    Убираем регистр, лишние пробелы и конечную пунктуацию. Слова, числа и
    отрицания сохраняем: «500 м» нельзя превратить в «50 м», «не хочу» — в «хочу».
    Это не NLP-анализ и не поиск по смысловой близости.
    """
    return ' '.join(text.lower().strip().rstrip('.!?').split())


def llm_schema() -> dict:
    """JSON Schema для LLM: контракт ParsedHotelQuery минус поля, которые задаёт backend.

    enum ограничивает имена фич текущим YAML-реестром: модель не должна
    придумывать sea_view_probability или несуществующий инструмент.
    Расчётных спутников (derived_from, weight_source=companion) добавляет
    app/ml/companions.py после разбора, модель их не выводит.
    """
    schema = ParsedHotelQuery.model_json_schema()
    for name in ('HardConstraint', 'SoftPreference'):
        schema['$defs'][name]['properties']['feature_key']['enum'] = list(get_registry().definitions)
    soft = schema['$defs']['SoftPreference']['properties']
    soft.pop('derived_from', None)
    schema['properties'].pop('ignored_terms', None)
    soft['weight_source']['enum'] = [v for v in soft['weight_source']['enum'] if v != 'companion']
    return schema


class FixtureQueryParser:
    """Детерминированный офлайн-провайдер для воспроизводимой демонстрации."""
    mode = 'fixture'

    def __init__(self, path=ROOT / 'data/demo/query_fixtures.json'):
        # JSON содержит пары text → expected. Список examples также нужен UI.
        self.examples = json.loads(path.read_text())
        # Словарь даёт быстрый поиск по нормализованному тексту.
        self.fixtures = {
            normalize(example['text']): example['expected']
            for example in self.examples
        }

    def parse(self, text: str) -> ParsedHotelQuery:
        raw = self.fixtures.get(normalize(text))
        if raw is None:
            # НЕ выбираем «похожий» запрос: так можно потерять отрицание/число.
            # API увидит unknown_or_ambiguous и остановит подбор для уточнения.
            return ParsedHotelQuery(
                original_text=text,
                unknown_or_ambiguous=['Запрос вне набора демо-парсера'],
                clarification_question=(
                    'Выберите пример демо или включите PARSER_MODE=ollama '
                    'для свободного текста.'
                ),
            )

        # Даже подготовленный JSON проходит тот же Pydantic-контракт, что и LLM.
        # Оператор | создаёт новый dict: сохранённый fixture не изменяется.
        return ParsedHotelQuery.model_validate(raw | {'original_text': text})


class OfflineQueryParser:
    """Без ключей и сети: точное совпадение с демо-примером, иначе правила.

    Демо-формулировки дают проверенный эталонный ответ; любой другой текст
    разбирается RulesQueryParser по словарю реестра. Неизвестное не угадывается.
    """
    mode = 'offline'

    def __init__(self):
        from app.ml.rules_parser import RulesQueryParser
        self.fixture = FixtureQueryParser()
        self.rules = RulesQueryParser()
        self.examples = self.fixture.examples

    def parse(self, text: str) -> ParsedHotelQuery:
        if normalize(text) in self.fixture.fixtures:
            return self.fixture.parse(text)
        return self.rules.parse(text)


class OllamaQueryParser:
    """Адаптер готовой модели: schema → HTTP → проверенный Python-объект.

    client можно передать извне. В тестах вместо настоящего сервера используется
    httpx.MockTransport: проверяется наш код, без скачивания модели и сети.
    Это НЕ измерение качества самой модели; для него нужен evaluate_parser.
    """
    mode = 'ollama'

    def __init__(self, config=settings, client=None):
        self.config = config
        # Соединение должно установиться за 5 с; ожидание ответа — до 60 с.
        self.client = client or httpx.Client(timeout=httpx.Timeout(config.parser_timeout_seconds, connect=5))

    def parse(self, text: str) -> ParsedHotelQuery:
        from app.ml.prompts import query_messages

        # Шаг 1. Получаем JSON Schema автоматически из Pydantic-класса.
        # Так описание для LLM и контракт backend не расходятся вручную.
        schema = llm_schema()

        # Шаг 2. Готовим запрос Ollama /api/chat.
        # format=schema ограничивает структуру ответа; сообщения объясняют смысл.
        # temperature=0 уменьшает случайность, но НЕ гарантирует истинность.
        # num_predict ограничивает длину вывода. stream=False даёт единый JSON.
        payload = {
            'model': self.config.model_name,
            'stream': False,
            'format': schema,
            'options': {'temperature': 0, 'num_predict': 3000, 'num_ctx':self.config.ollama_num_ctx},
            'messages': query_messages(text, schema),
        }

        # Шаг 3. Максимум две попытки. Бесконечный retry заморозил бы интерфейс.
        for attempt in range(2):
            try:
                response = self.client.post(
                    self.config.ollama_url.rstrip('/') + '/api/chat',
                    json=payload,
                )
                # HTTP 4xx/5xx превращаются в исключение, а не «успешный поиск».
                response.raise_for_status()

                # Шаг 4. Structured output тоже проверяем: типы, операторы,
                # feature_key, scope, единицы, диапазоны. Число вместо bool,
                # неизвестный ключ и плохой JSON не проходят дальше.
                content = response.json()['message']['content']
                parsed = ParsedHotelQuery.model_validate_json(content)

                # Для аудита берём реальный ввод; не доверяем его пересказу LLM.
                parsed.original_text = text
                return parsed
            except (httpx.HTTPError, ValidationError, KeyError, TypeError, ValueError) as exc:
                if attempt == 1:
                    # Никакого скрытого fallback: ошибка модели не означает,
                    # что следует заменить запрос одним из demo-примеров.
                    raise ParserError(
                        'Ollama недоступна или вернула невалидный контракт; '
                        'фильтры не подменены.'
                    ) from exc
                time.sleep(.2)
        raise ParserError('unreachable')


class GroqQueryParser:
    """Облачная альтернатива без GPU: одинаковый контракт для разных моделей.

Аккаунт с Free Plan нужен пользователю. Мы не включаем платный план и не
обещаем неограниченную квоту. Ключ остаётся на backend. Во внешний сервис
отправляются текст запроса и примеры, но не база гостиниц/ответы отельеров.
JSON-schema best-effort сохраняет необязательные поля Pydantic; локальная
валидация обязательна. Ошибка API или 429 не подменяется демо-результатом.
"""
    mode = 'groq'

    def __init__(self, config=settings, client=None):
        self.config = config
        self.client = client or httpx.Client(timeout=httpx.Timeout(config.parser_timeout_seconds, connect=5))

    def parse(self, text):
        from app.ml.prompts import query_messages
        if not self.config.groq_api_key:
            raise ParserError('Добавьте GROQ_API_KEY в локальный .env; облачная модель ещё не подключена.')
        schema = llm_schema()
        payload = {'model':self.config.groq_model, 'messages':query_messages(text,schema),
                   'temperature':0, 'max_completion_tokens':3000,
                   'reasoning_effort':'low',
                   'response_format':{'type':'json_schema','json_schema':{
                       'name':'hotel_query','strict':False,'schema':schema}}}
        # Одна повторная попытка только для ошибочного контракта. 401/429/5xx
        # завершаются сразу: повторять исчерпанную квоту в цикле бессмысленно.
        for attempt in range(2):
            try:
                response = self.client.post('https://api.groq.com/openai/v1/chat/completions',
                    headers={'Authorization':'Bearer '+self.config.groq_api_key}, json=payload)
                if response.is_error:
                    raise ParserError(f'Groq HTTP {response.status_code}: проверьте ключ, доступность модели и бесплатную квоту.')
                raw = response.json()
                if raw['choices'][0].get('finish_reason') != 'stop':
                    raise ValueError('Незавершённый ответ модели')
                parsed = ParsedHotelQuery.model_validate_json(raw['choices'][0]['message']['content'])
                parsed.original_text = text
                return parsed
            except httpx.HTTPError as exc:
                raise ParserError('Groq недоступен по сети; запрос не подменён.') from exc
            except (ValidationError, KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, ParserError):
                    raise
                if attempt == 1:
                    raise ParserError('Groq вернул невалидный контракт; фильтры не подменены.') from exc
        raise ParserError('unreachable')


def make_parser(config=settings) -> QueryParser:
    """Фабрика выбирает провайдер один раз при создании FastAPI-приложения."""
    if config.parser_mode == 'offline':
        return OfflineQueryParser()
    if config.parser_mode == 'fixture':
        return FixtureQueryParser()
    if config.parser_mode == 'ollama':
        return OllamaQueryParser(config)
    if config.parser_mode == 'groq':
        return GroqQueryParser(config)
    raise ValueError('PARSER_MODE должен быть offline, fixture, ollama или groq')
