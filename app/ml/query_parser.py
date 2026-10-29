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


class QueryParserUnavailable(ParserError):
    """Ключ/модель/сервис недоступны; API вернёт 503 без подмены запроса."""


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
    from app.ml.prompts import query_features
    schema = ParsedHotelQuery.model_json_schema()
    for name in ('HardConstraint', 'SoftPreference'):
        # Только признаки с query_hint: расчётные спутники и aircraft_noise_exposure
        # модель путала с желаниями гостя (выбирала их вместо aircraft_path_distance_m).
        schema['$defs'][name]['properties']['feature_key']['enum'] = list(query_features())
    # Pydantic допускает unit=None/scope=hotel по умолчанию, но для числовой
    # фичи валидатор требует unit=m, для признака номера — scope=room.
    # Без required модель могла законно (по JSON Schema) опустить эти поля,
    # после чего тот же ответ отклонялся предметным валидатором Pydantic.
    schema['$defs']['HardConstraint']['required'] = list(schema['$defs']['HardConstraint']['properties'])
    # Потребности: варианты понятий и выбор гостя заполняет backend, не модель.
    from app.features.concepts import get_concepts
    need = schema['$defs']['Need']['properties']
    need.pop('options', None)
    need.pop('chosen', None)
    need.pop('question', None)
    schema['$defs'].pop('NeedOption', None)
    need['features']['items']['enum'] = list(query_features())
    need['concept'] = {'anyOf': [{'type': 'string', 'enum': list(get_concepts())}, {'type': 'null'}]}
    schema['$defs']['Need']['required'] = list(need)
    soft = schema['$defs']['SoftPreference']['properties']
    soft.pop('derived_from', None)
    schema['properties'].pop('ignored_terms', None)
    # Исходный текст уже есть у сервера. Просить LLM переписывать его лишнее.
    schema['properties'].pop('original_text', None)
    # Не разрешаем молча пропускать списки и источник веса: иначе default
    # Pydantic скрывает пропуск и может затереть явный вес пользователя.
    schema['required'] = list(schema['properties'])
    schema['$defs']['SoftPreference']['required'] = list(soft)
    soft['weight_source']['enum'] = [v for v in soft['weight_source']['enum'] if v != 'companion']
    return schema


def registry_fields(raw):
    """scope и unit признака однозначно заданы реестром — не заставляем модель их угадывать.

    Gemma на «Тихий номер…» ставила тишине scope=room: ответ отклонялся и повторялся
    (+7 с). Подставляем значения из реестра; unit=km оставляем — контракт сам
    переводит километры в метры. Неизвестный feature_key не трогаем: его отклонит Pydantic.
    """
    if not isinstance(raw, dict):
        return raw
    # Вспомогательная разметка needs чинится отдельно — огрех в ней не роняет разбор.
    from app.ml.needs import clean_llm_needs
    clean_llm_needs(raw)
    registry = get_registry().definitions
    for kind in ('hard_constraints', 'soft_preferences'):
        for item in raw.get(kind) or []:
            definition = registry.get(item.get('feature_key')) if isinstance(item, dict) else None
            if definition is None:
                continue
            item['scope'] = definition.scope
            if kind == 'hard_constraints' and item.get('unit') != 'km':
                item['unit'] = definition.unit
    return raw


def mentioned_numbers(text: str) -> set[float]:
    """Все величины, которые можно честно вывести из чисел запроса.

    Число N даёт N, N км → метры (N*1000) и N пеших минут (N*80 м). Слова
    («двух», «полкилометра») нормализует тот же код, что и офлайн-правила.
    """
    import re
    from app.ml.rules_parser import normalize as rules_normalize, WALK_M_PER_MINUTE
    lowered = rules_normalize(text)
    values = {500.0} if 'полкилометр' in lowered else set()
    if re.search(r'\bкилометр', lowered):
        values.add(1000.0)
    for raw in re.findall(r'\d+(?:[.,]\d+)?', lowered):
        number = float(raw.replace(',', '.'))
        values |= {number, round(number * 1000, 6), number * WALK_M_PER_MINUTE}
    return values


def drop_invented_numbers(parsed: ParsedHotelQuery, text: str) -> ParsedHotelQuery:
    """Убирает числа, которых нет в запросе: LLM иногда дописывала «пляж <= 500 м».

    Hard-условие с выдуманным пределом удаляется целиком (гость его не ставил),
    у soft выдуманная utility-кривая сбрасывается — само желание остаётся.
    tolerance не проверяем: «к 500 м неудобно» при идеале 200 м законно даёт 300.
    """
    numbers = mentioned_numbers(text)
    known = lambda value: any(abs(value - n) < 1e-6 for n in numbers)
    parsed.hard_constraints = [c for c in parsed.hard_constraints
                               if type(c.value) not in (int, float) or known(float(c.value))]
    for preference in parsed.soft_preferences:
        curve = preference.utility
        if curve and not all(known(v) for v in (curve.ideal_min, curve.ideal_max) if v is not None):
            preference.utility = None
    return parsed


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
            'options': {'temperature': self.config.temperature,
                        'num_predict': self.config.max_output_tokens,
                        'num_ctx': self.config.ollama_num_ctx},
            'messages': query_messages(text, schema),
        }
        payload['keep_alive'] = self.config.ollama_keep_alive
        if self.config.ollama_think is not None:
            # Qwen3 по умолчанию сначала «рассуждает» текстом: это время и токены
            # без пользы для извлечения полей. think=false — сразу ответ по схеме.
            payload['think'] = self.config.ollama_think

        # Шаг 3. До двух попыток при невалидном контракте; отказ сети/сервиса — сразу.
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
                parsed = ParsedHotelQuery.model_validate(registry_fields(json.loads(content)))

                # Для аудита берём реальный ввод; не доверяем его пересказу LLM.
                parsed.original_text = text
                return drop_invented_numbers(parsed, text)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in (401, 403, 404, 408, 429) or status >= 500:
                    raise QueryParserUnavailable(f'Ollama HTTP {status}: сервис или модель недоступны.') from exc
                raise ParserError(f'Ollama отклонила запрос (HTTP {status}); фильтры не подменены.') from exc
            except httpx.HTTPError as exc:
                raise QueryParserUnavailable('Ollama недоступна по сети; фильтры не подменены.') from exc
            except (ValidationError, KeyError, TypeError, ValueError) as exc:
                if attempt == 1:
                    # Никакого скрытого fallback: ошибка модели не означает,
                    # что следует заменить запрос одним из demo-примеров.
                    raise ParserError(
                        'Ollama недоступна или вернула невалидный контракт; '
                        'фильтры не подменены.'
                    ) from exc
                if isinstance(exc, ValidationError):
                    # Повтор того же запроса при temperature=0 часто повторяет
                    # ту же ошибку. Даём модели адрес и причину нарушения схемы,
                    # без секретов и без эталонных ответов из evaluation-набора.
                    payload['messages'].extend([{'role': 'assistant', 'content': content},
                        {'role': 'user', 'content':
                        'Ответ не прошёл проверку контракта. Исправь JSON для того же запроса. '
                        'Неподдержанное условие помести в unknown_or_ambiguous. Ошибки: '
                        + json.dumps(exc.errors(include_url=False, include_context=False, include_input=False), ensure_ascii=False)
                        + '\nИсходный запрос (JSON-строка): ' + json.dumps(text, ensure_ascii=False)}])
                time.sleep(.2)
        raise ParserError('unreachable')


def warm_up_ollama(config, client) -> None:
    """Загружает модель в память заранее: иначе первый запрос гостя ждёт ~30 с.

    Пустой /api/generate только загружает веса (документированное поведение Ollama).
    Ошибки молча игнорируются: без Ollama гибрид всё равно работает на правилах.
    """
    try:
        client.post(config.ollama_url.rstrip('/') + '/api/generate',
                    json={'model': config.model_name, 'keep_alive': config.ollama_keep_alive},
                    timeout=httpx.Timeout(180, connect=5))
    except Exception:
        pass


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
            raise QueryParserUnavailable('Добавьте GROQ_API_KEY в локальный .env; облачная модель ещё не подключена.')
        schema = llm_schema()
        payload = {'model':self.config.groq_model, 'messages':query_messages(text,schema),
                   'temperature':self.config.temperature,
                   'max_completion_tokens':self.config.max_output_tokens,
                   'reasoning_effort':self.config.groq_reasoning_effort,
                   'response_format':{'type':'json_schema','json_schema':{
                       'name':'hotel_query','strict':False,'schema':schema}}}
        # Одна повторная попытка только для ошибочного контракта. 401/429/5xx
        # завершаются сразу: повторять исчерпанную квоту в цикле бессмысленно.
        for attempt in range(2):
            try:
                response = self.client.post(self.config.cloud_base_url + '/chat/completions',
                    headers={'Authorization':'Bearer '+self.config.groq_api_key}, json=payload)
                if response.is_error:
                    if response.status_code in (401, 403, 404, 408, 429) or response.status_code >= 500:
                        raise QueryParserUnavailable(f'Groq HTTP {response.status_code}: проверьте ключ, модель и квоту.')
                    raise ParserError(f'Groq HTTP {response.status_code}: проверьте ключ, доступность модели и бесплатную квоту.')
                raw = response.json()
                if raw['choices'][0].get('finish_reason') != 'stop':
                    raise ValueError('Незавершённый ответ модели')
                parsed = ParsedHotelQuery.model_validate(registry_fields(json.loads(raw['choices'][0]['message']['content'])))
                parsed.original_text = text
                return drop_invented_numbers(parsed, text)
            except httpx.HTTPError as exc:
                raise QueryParserUnavailable('Groq недоступен по сети; запрос не подменён.') from exc
            except (ValidationError, KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, ParserError):
                    raise
                if attempt == 1:
                    raise ParserError('Groq вернул невалидный контракт; фильтры не подменены.') from exc
        raise ParserError('unreachable')


class HybridQueryParser:
    """Сначала правила, LLM — только для того, что правила не разобрали.

    Правила детерминированы и не выдумывают условий, но знают лишь словарь
    реестра. Если после них не осталось несопоставленных слов (ignored_terms)
    и найдено хоть что-то, их ответ окончательный. Иначе вызывается LLM, но её
    ответ НЕ заменяет правила: она лишь добавляет признаки, которых правила не
    нашли. Замер 29.10: при полной замене Gemma на 9 из 36 запросов портила
    верный разбор правил (переворачивала desired, теряла условия).
    Недоступная LLM не ломает поиск: вернётся разбор правил, а несопоставленные
    слова по-прежнему показываются гостю как «не учтено».
    """
    mode = 'hybrid'
    NOTHING_FOUND = 'Не нашёл поддерживаемых пожеланий'

    def __init__(self, config=settings, llm=None):
        self.offline = OfflineQueryParser()
        self.examples = self.offline.examples
        self.llm = llm or (GroqQueryParser(config) if config.hybrid_llm == 'groq' else OllamaQueryParser(config))
        self.client = self.llm.client
        self.last_source = None  # 'rules' | 'llm' | 'rules_fallback' — для отчётов и отладки

    def warm_up(self) -> None:
        if isinstance(self.llm, OllamaQueryParser):
            warm_up_ollama(self.llm.config, self.llm.client)
            # Загрузки весов мало: первый разбор ещё ~30 с читает длинный промпт
            # (реестр + примеры, ~5.5 тыс. токенов). Пробный разбор кладёт этот общий
            # префикс в кэш Ollama — запросы гостей дальше идут за несколько секунд.
            try:
                self.llm.parse('Тихий отель у моря')
            except Exception:
                pass

    def rules_are_enough(self, parsed: ParsedHotelQuery) -> bool:
        return not parsed.ignored_terms and self.NOTHING_FOUND not in parsed.unknown_or_ambiguous

    def parse(self, text: str) -> ParsedHotelQuery:
        rules = self.offline.parse(text)
        if self.rules_are_enough(rules):
            self.last_source = 'rules'
            return rules
        try:
            llm = self.llm.parse(text)
        except ParserError:
            self.last_source = 'rules_fallback'
            return rules
        self.last_source = 'llm'
        return self.merge(rules, llm)

    def merge(self, rules: ParsedHotelQuery, llm: ParsedHotelQuery) -> ParsedHotelQuery:
        """Правила + новые признаки LLM. Признак, найденный правилами, LLM не трогает."""
        nothing = self.NOTHING_FOUND in rules.unknown_or_ambiguous
        if nothing:
            # Правила ничего не поняли — ответ LLM целиком (кроме пустого).
            if (not llm.hard_constraints and not llm.soft_preferences and not llm.unknown_or_ambiguous
                    and not llm.needs and not llm.unsupported):
                return rules
            return llm
        known = {c.feature_key for c in rules.hard_constraints} | {p.feature_key for p in rules.soft_preferences}
        hard = rules.hard_constraints + [c for c in llm.hard_constraints if c.feature_key not in known]
        soft = rules.soft_preferences + [p for p in llm.soft_preferences if p.feature_key not in known]
        # Вопросы LLM здесь поиск не блокируют: правила уже что-то нашли, а Gemma
        # часто пишет расплывчатое «уточните способ измерения» к понятному запросу.
        # Блокируют только точные пометки правил; расплывчатое («вид из окна») —
        # потребность any_of, а не вопрос.
        unknown = rules.unknown_or_ambiguous
        merged_needs = self.merge_needs(rules, llm, hard, soft)
        # Непонятые слова скрываем, только если LLM их «покрыла»: добавила признак,
        # потребность или тему либо подтвердила разбор правил, ничего не оставив под
        # сомнением. Иначе гость видит «Не учтено: …» и понимает, что часть запроса не учтена.
        llm_keys = {c.feature_key for c in llm.hard_constraints} | {p.feature_key for p in llm.soft_preferences}
        covered = bool(llm_keys or llm.needs or llm.unsupported) and not llm.unknown_or_ambiguous
        return ParsedHotelQuery(
            region=llm.region if rules.region == 'other' else rules.region,
            hard_constraints=hard, soft_preferences=soft, unknown_or_ambiguous=unknown,
            clarification_question=rules.clarification_question if unknown else None,
            original_text=rules.original_text, ignored_terms=[] if covered else rules.ignored_terms,
            unsupported=rules.unsupported + [u for u in llm.unsupported if u not in rules.unsupported],
            needs=merged_needs)

    @staticmethod
    def merge_needs(rules: ParsedHotelQuery, llm: ParsedHotelQuery, hard, soft):
        """Потребности правил + новые от LLM (по признакам, понятиям и темам, которых правила не нашли)."""
        keys = {c.feature_key for c in hard} | {p.feature_key for p in soft}
        needs = list(rules.needs)
        seen_features = {k for n in needs for k in n.features}
        seen_concepts = {n.concept for n in needs if n.kind == 'any_of'}
        seen_topics = {n.topic for n in needs if n.kind == 'unsupported'}
        for need in llm.needs:
            if need.kind == 'feature':
                fresh = [k for k in need.features if k not in seen_features and k in keys]
                if fresh:
                    needs.append(need.model_copy(update={'features': fresh}))
                    seen_features |= set(fresh)
            elif need.kind == 'any_of' and need.concept not in seen_concepts:
                needs.append(need)
                seen_concepts.add(need.concept)
            elif need.kind == 'unsupported' and need.topic not in seen_topics:
                needs.append(need)
                seen_topics.add(need.topic)
        return needs


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
    if config.parser_mode == 'hybrid':
        return HybridQueryParser(config)
    raise ValueError('PARSER_MODE должен быть offline, fixture, ollama, groq или hybrid')
