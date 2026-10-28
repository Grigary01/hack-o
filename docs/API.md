# API v0.1

Base URL: `http://127.0.0.1:8000`. OpenAPI: `/openapi.json`, Swagger: `/docs`.
JSON-контракты: `app/schemas/*`; примеры фактических ответов — `docs/examples/`.
Актуальные типы, коды ошибок и экран конфликтов:
[API_FRONTEND_INTEGRATION](API_FRONTEND_INTEGRATION.md).
Переносимые файлы: [OpenAPI](examples/backend_api_openapi.json),
[JSON-примеры](examples/backend_api_examples.json).

| Метод и путь | Вход | Результат |
|---|---|---|
| GET /api/health | — | DB/seed count, parser_mode, demo_mode; внешние API не проверяет |
| GET /api/features | — | декларации YAML |
| GET /api/demo-queries | — | 13 поддерживаемых demo-формулировок |
| POST /api/parse-query | `text` | ParsedHotelQuery |
| POST /api/search | text **или** parsed, weights, include_simulated | matched / needs_verification / excluded + trace |
| GET /api/hotels | — | список Hotel |
| GET /api/hotels/{id} | OSM ID с префиксом `osm:type:id` | hotel, observations, conflicts |
| GET /api/hotels/{id}/evidence | — | история, current_real/current_demo, conflicts |
| GET /api/hotelier/questions | hotel_id?, status=open/answered? | очередь с context и updated_at; TTL пересчитывается до фильтра |
| POST /api/hotelier/questions | hotel_id, feature_key | вопрос (идемпотентно) |
| POST /api/hotelier/questions/{qid}/answer | text | pending answer + extraction |
| GET /api/hotelier/answers/{aid} | — | сохранённый HotelierAnswer |
| POST /api/hotelier/answers/{aid}/confirm | accept: boolean | AnswerConfirmation: статус, те же ID при повторе, конфликты, вопрос |
| GET /api/hotelier/conflicts | hotel_id?, status=open/resolved? | ConflictDetail[] с обеими версиями и решением |
| POST /api/hotelier/conflicts/{id}/resolve | selected_observation_id, reason | решение, idempotent, текущее demo-состояние |

## Пример

```bash
curl http://127.0.0.1:8000/api/parse-query \
  -H 'Content-Type: application/json' \
  -d '{"text":"Хочу тихий отель не дальше 500 метров пешком от пляжа"}'

curl http://127.0.0.1:8000/api/search \
  -H 'Content-Type: application/json' \
  -d '{"text":"Ищу тихий отель в Адлере, не дальше 500 метров пешком от пляжа, хотелось бы вид на море","weights":{"quietness_proxy":0.9,"sea_view":0.6}}'
```

Распознанное строгое условие: walking_distance_to_beach_m <= 500 m / hotel.
Мягкие: quietness_proxy high / hotel, sea_view true / room.
На snapshot от 23.10.2026 первая карточка — OSM `osm:node:10058556917`, «Островок»:
319.8 м по графу с оценочными отрезками привязки; quietness high; sea_view неизвестен;
score=1.0, coverage=.6, ranking_score=.6. Совпадение названия с брендом хакатона не означает аффилированность.
Полный source/date/method и геометрия — в сохранённом JSON-ответе.

## Правила и ошибки

- `eligible=true`: строгие условия соблюдены по используемым данным; для оценок остаются warnings.
- `eligible=null`: нужны данные; `eligible=false`: проверенное нарушение hotel-условия.
- `status=needs_clarification` — нормальный HTTP 200, но списки результатов пусты. UI должен показать вопрос.
- 422: невалидные типы, scope/unit, неизвестный key, некорректные веса, попытка подтвердить неполный разбор.
- 404: отсутствующий hotel/question/answer.
- 409: несовместимое повторное решение или подтверждение.
- 503: база не заполнена либо модель/ключ/сервис недоступны.
- 502: результат модели не прошёл валидацию или провайдер отклонил контракт.
- 403: кабинет/симуляция отключены в `DEMO_MODE=false`.

Ошибки содержат `code` и прежний `detail` (строка или список ошибок Pydantic).

Числа не принимают bool, NaN/Infinity запрещены. Boolean/category поддерживают только = и !=;
числовые — <, <=, =, >=, >, !=. Км нормализуются в метры, другие единицы отвергаются.
Вес можно менять только у soft preference из текущего запроса. Text и parsed одновременно запрещены.

Локальный API не имеет авторизации, рассчитан на bind **127.0.0.1**. Production размещение
и контроль владельца отеля — следующие задачи. Миграции SQLite реализованы:
[инструкция](MIGRATIONS.md). Контракт решения конфликтов, ошибки 404/409/422,
JSON-примеры и заглушки для участников: [CONFLICT_INTEGRATION](CONFLICT_INTEGRATION.md).
Жизненный цикл вопросов, причины открытия и клиент очереди:
[QUESTION_INTEGRATION](QUESTION_INTEGRATION.md).
Заменяемый обработчик ответа отельера, схема и ошибки 502/503:
[REPLY_PARSER_INTEGRATION](REPLY_PARSER_INTEGRATION.md).

## Расширение 26 октября: среда, модели, ранжирование

- GET /api/hotels/{hotel_id}/environment — последние noise/air_quality отчёты,
  исходные даты и флаг cache_stale. Отсутствие отчёта — not_collected.
- POST /api/hotels/{hotel_id}/environment/air-quality/refresh — явный сетевой
  запрос OpenAQ и сохранение отчёта. При отсутствии ключа — not_configured;
  при недоступности upstream — provider_error, без ложного «станций нет».
- POST /api/search принимает ranking_method: balanced_v2 (default) или weighted_v1,
  balance в [0,1] (default .25). В ответе ranking_interval, group_scores,
  pareto_dominated; с этапа 5 также фактический balance. Hard/unknown/same-room политика не изменена.
- SoftPreference.utility: null или {kind: lower|higher|target_range,
  ideal_min, ideal_max, tolerance}. Числа в единицах фичи, tolerance > 0.
- PARSER_MODE=groq: облачный parser; невалидный вывод — 502, отсутствие ключа,
  отказ сети/модели/квоты — 503. Запрос не подменяется fixture.

Схемы и примеры: [MODELS_AND_RANKING](MODELS_AND_RANKING.md),
[ENVIRONMENT](ENVIRONMENT.md). HTTP-запуска произвольных Java-скриптов нет.
