# Структура и ответственность по файлам

Имена четырёх участников не переданы: **У1 — ML**, **У2 — Geo/Data**, **У3 — Backend/Agent/Storage**,
**У4 — Frontend**. Владелец отвечает за понятность, изменение и проверки файла; контракты `app/schemas/`
согласуют У1–У3. У3 координирует документацию, У4 помогает с интеграционным QA. Входные документы и legacy
закреплены за У3 для сохранности; авторство этих материалов не присваивается.

Ниже все файлы исходной поставки. Пустые `__init__.py` объявляют пакеты и не являются TODO-заглушками.
`docs/inputs/` — первоначальные материалы пользователя, они не заменяют актуальные README/TASKS.

```text
ostrovok-adler-mvp/
├── app/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── feature_agent.py
│   │   └── tool_registry.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py
│   │   ├── hotelier.py
│   │   ├── hotels.py
│   │   └── search.py
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py
│   ├── features/
│   │   ├── __init__.py
│   │   ├── registry.py
│   │   ├── registry.yaml
│   │   └── service.py
│   ├── geo/
│   │   ├── __init__.py
│   │   ├── geometry.py
│   │   ├── osm_provider.py
│   │   ├── quietness.py
│   │   ├── routing.py
│   │   └── service.py
│   ├── hotelier/
│   │   ├── __init__.py
│   │   └── dialogue.py
│   ├── ml/
│   │   ├── __init__.py
│   │   ├── prompts.py
│   │   ├── query_parser.py
│   │   └── ranking.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── hotel.py
│   │   ├── hotelier.py
│   │   ├── query.py
│   │   └── search.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── db.py
│   │   ├── models.py
│   │   └── repository.py
│   ├── __init__.py
│   └── main.py
├── data/
│   ├── demo/
│   │   ├── osm_cache/
│   │   │   └── faba8255373fdc470c2bbd14ccf9ece99d827786.json
│   │   ├── features.json
│   │   ├── graph_metadata.json
│   │   ├── hotels.json
│   │   ├── osm_snapshot.json
│   │   ├── quality_report.json
│   │   ├── query_fixtures.json
│   │   ├── region.json
│   │   └── walk.graphml
│   └── evaluation/
│       ├── parser_metrics_fixture.json
│       └── queries_gold.jsonl
├── docs/
│   ├── examples/
│   │   ├── parse_response.json
│   │   ├── pytest_results.xml
│   │   └── search_response.json
│   ├── inputs/
│   │   ├── ostrovok_adler_blueprint/
│   │   │   ├── ARCHITECTURE.md
│   │   │   ├── CODE_SKETCH.md
│   │   │   ├── PROMPT_CODING_AGENT.md
│   │   │   ├── START_HERE.md
│   │   │   └── TEAM_TASKS.md
│   │   └── HACKATHON_TASK.txt
│   ├── API.md
│   ├── ARCHITECTURE.md
│   ├── DATA_SOURCES.md
│   ├── FEATURE_REGISTRY.md
│   ├── ML_GUIDE.md
│   ├── PIPELINE.md
│   ├── PROJECT_STRUCTURE.md
│   ├── REPO_AUDIT.md
│   ├── TASKS.md
│   └── VALIDATION.md
├── frontend/
│   ├── __init__.py
│   ├── api_client.py
│   ├── app.py
│   └── map_view.py
├── legacy/
│   ├── README.md
│   └── agent_tool_map_45ad71a.zip
├── scripts/
│   ├── __init__.py
│   ├── collect_adler_osm.py
│   ├── compute_geo_features.py
│   ├── evaluate_parser.py
│   ├── package_demo.py
│   ├── seed_demo.py
│   └── validate_data.py
├── tests/
│   ├── conftest.py
│   ├── test_api_smoke.py
│   ├── test_conflicts.py
│   ├── test_evaluation.py
│   ├── test_feature_agent.py
│   ├── test_frontend.py
│   ├── test_geo_routes.py
│   ├── test_hotelier.py
│   ├── test_query_parser.py
│   ├── test_ranking.py
│   └── test_streamlit_flow.py
├── .env.example
├── .gitignore
├── LICENSE
├── README.md
├── THIRD_PARTY_NOTICES.md
├── pyproject.toml
└── requirements.lock
```

## Пофайловое закрепление

| Файл | Ответственный | Что делает / за что отвечает |
|---|---|---|
| [.env.example](../.env.example) | У3 · Backend/Agent/Storage | Пример конфигурации без секретов: parser, модель, БД и адреса сервисов. |
| [.gitignore](../.gitignore) | У3 · Backend/Agent/Storage | Исключает локальную среду, рабочую БД, секреты и генерируемые архивы. |
| [LICENSE](../LICENSE) | У3 · Backend/Agent/Storage | Исходная MIT-лицензия Maxim сохранена без изменений. |
| [README.md](../README.md) | У3 · Backend/Agent/Storage | Команды запуска, демонстрация и навигация для всей команды. |
| [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) | У3 · Backend/Agent/Storage | Авторство заимствований, исходный commit и лицензия OSM. |
| [app/__init__.py](../app/__init__.py) | У3 · Backend/Agent/Storage | Объявляет Python-пакет; отдельной бизнес-логики нет. |
| [app/agent/__init__.py](../app/agent/__init__.py) | У3 · Backend/Agent/Storage | Объявляет Python-пакет; отдельной бизнес-логики нет. |
| [app/agent/feature_agent.py](../app/agent/feature_agent.py) | У3 · Backend/Agent/Storage | Constrained planner: выбирает cache, Geo provider или вопрос по реестру. |
| [app/agent/tool_registry.py](../app/agent/tool_registry.py) | У3 · Backend/Agent/Storage | Whitelist, типизированные аргументы, ограниченный бюджет. Нет eval/getattr по LLM. |
| [app/api/__init__.py](../app/api/__init__.py) | У3 · Backend/Agent/Storage | Объявляет Python-пакет; отдельной бизнес-логики нет. |
| [app/api/dependencies.py](../app/api/dependencies.py) | У3 · Backend/Agent/Storage | Транзакционный Repository для FastAPI. |
| [app/api/hotelier.py](../app/api/hotelier.py) | У3 · Backend/Agent/Storage | Локальные вопросы, ответы и подтверждение с проверкой demo mode. |
| [app/api/hotels.py](../app/api/hotels.py) | У3 · Backend/Agent/Storage | Чтение отелей, evidence, реестра и demo-запросов. |
| [app/api/search.py](../app/api/search.py) | У3 · Backend/Agent/Storage | Parse/search: planner, пользовательские веса, группы и trace. |
| [app/core/__init__.py](../app/core/__init__.py) | У3 · Backend/Agent/Storage | Объявляет Python-пакет; отдельной бизнес-логики нет. |
| [app/core/config.py](../app/core/config.py) | У3 · Backend/Agent/Storage | Конфигурация среды и единый корень проекта. |
| [app/features/__init__.py](../app/features/__init__.py) | У3 · Backend/Agent/Storage | Объявляет Python-пакет; отдельной бизнес-логики нет. |
| [app/features/registry.py](../app/features/registry.py) | У3 · Backend/Agent/Storage | Загрузка/проверка YAML и типов значений. |
| [app/features/registry.yaml](../app/features/registry.yaml) | У3 · Backend/Agent/Storage | Тип, scope, provider, TTL, веса, алиасы и вопросы для шести признаков. |
| [app/features/service.py](../app/features/service.py) | У3 · Backend/Agent/Storage | Текущее знание — представление над неизменяемой историей наблюдений. |
| [app/geo/__init__.py](../app/geo/__init__.py) | У2 · Geo/Data | Объявляет Python-пакет; отдельной бизнес-логики нет. |
| [app/geo/geometry.py](../app/geo/geometry.py) | У2 · Geo/Data | Метры в UTM37N, преобразования геометрии и привязка. |
| [app/geo/osm_provider.py](../app/geo/osm_provider.py) | У2 · Geo/Data | OSM ingestion: union запросов, тип+ID, JSON cache и явные ошибки. |
| [app/geo/quietness.py](../app/geo/quietness.py) | У2 · Geo/Data | Прозрачная, НЕ калиброванная модель внешних источников шума. |
| [app/geo/routing.py](../app/geo/routing.py) | У2 · Geo/Data | Путь по рёбрам OSM walking graph. Никакого geodesic fallback. |
| [app/geo/service.py](../app/geo/service.py) | У2 · Geo/Data | Geo tools возвращают Observation с исходной датой snapshot, а не сегодняшним TTL. |
| [app/hotelier/__init__.py](../app/hotelier/__init__.py) | У3 · Backend/Agent/Storage | Объявляет Python-пакет; отдельной бизнес-логики нет. |
| [app/hotelier/dialogue.py](../app/hotelier/dialogue.py) | У3 · Backend/Agent/Storage | Ограниченный offline-парсер свободных ответов; неизвестные конструкции не угадывает. |
| [app/main.py](../app/main.py) | У3 · Backend/Agent/Storage | FastAPI composition root. Не выгружает OSM и не заполняет demo при импорте. |
| [app/ml/__init__.py](../app/ml/__init__.py) | У1 · ML | Объявляет Python-пакет; отдельной бизнес-логики нет. |
| [app/ml/prompts.py](../app/ml/prompts.py) | У1 · ML | Промпт — инструкции готовой LLM и примеры желаемого ответа. |
| [app/ml/query_parser.py](../app/ml/query_parser.py) | У1 · ML | Понимание пользовательского запроса: русский текст → ParsedHotelQuery. |
| [app/ml/ranking.py](../app/ml/ranking.py) | У1 · ML | Прозрачный подбор по фактам: строгая фильтрация + мягкое ранжирование. |
| [app/schemas/__init__.py](../app/schemas/__init__.py) | У3 · Backend/Agent/Storage | Объявляет Python-пакет; отдельной бизнес-логики нет. |
| [app/schemas/hotel.py](../app/schemas/hotel.py) | У3 · Backend/Agent/Storage | Hotel, Observation, Evidence и Source: типы и инварианты. |
| [app/schemas/hotelier.py](../app/schemas/hotelier.py) | У3 · Backend/Agent/Storage | Извлечённые утверждения и запросы кабинета. |
| [app/schemas/query.py](../app/schemas/query.py) | У1 · ML | ML → Backend контракт: форма результата понимания текста. |
| [app/schemas/search.py](../app/schemas/search.py) | У3 · Backend/Agent/Storage | Вход поиска, объяснения критериев и итоговые группы. |
| [app/storage/__init__.py](../app/storage/__init__.py) | У3 · Backend/Agent/Storage | Объявляет Python-пакет; отдельной бизнес-логики нет. |
| [app/storage/db.py](../app/storage/db.py) | У3 · Backend/Agent/Storage | SQLite engine, foreign keys и создание схемы. |
| [app/storage/models.py](../app/storage/models.py) | У3 · Backend/Agent/Storage | Таблицы SQLAlchemy, ключи, ограничения и история. |
| [app/storage/repository.py](../app/storage/repository.py) | У3 · Backend/Agent/Storage | Операции хранения, идемпотентность и поиск конфликтов. |
| [data/demo/features.json](../data/demo/features.json) | У2 · Geo/Data | 75 вычисленных наблюдений вместе с evidence. |
| [data/demo/graph_metadata.json](../data/demo/graph_metadata.json) | У2 · Geo/Data | Происхождение, размер и SHA256 графа. |
| [data/demo/hotels.json](../data/demo/hotels.json) | У2 · Geo/Data | 25 реальных OSM-отелей; входные данные seed. |
| [data/demo/osm_cache/faba8255373fdc470c2bbd14ccf9ece99d827786.json](../data/demo/osm_cache/faba8255373fdc470c2bbd14ccf9ece99d827786.json) | У2 · Geo/Data | Сырой кеш OSMnx для аудита происхождения графа. |
| [data/demo/osm_snapshot.json](../data/demo/osm_snapshot.json) | У2 · Geo/Data | Исходный ответ Overpass со временем и запросом. |
| [data/demo/quality_report.json](../data/demo/quality_report.json) | У2 · Geo/Data | Фактический результат проверки происхождения и пересчёта. |
| [data/demo/query_fixtures.json](../data/demo/query_fixtures.json) | У1 · ML | 12 точных формулировок офлайн-парсера и ожидаемые контракты. |
| [data/demo/region.json](../data/demo/region.json) | У2 · Geo/Data | Граница прибрежного Адлера и пороги привязки к графу. |
| [data/demo/walk.graphml](../data/demo/walk.graphml) | У2 · Geo/Data | Сохранённый пешеходный граф OSMnx. |
| [data/evaluation/parser_metrics_fixture.json](../data/evaluation/parser_metrics_fixture.json) | У1 · ML | Фактические метрики fixture, ошибки и expected/actual. |
| [data/evaluation/queries_gold.jsonl](../data/evaluation/queries_gold.jsonl) | У1 · ML | 44 вручную размеченных запроса: 12 demo, 32 held-out. |
| [docs/API.md](../docs/API.md) | У3 · Backend/Agent/Storage | Контракты REST и примеры запросов. |
| [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) | У3 · Backend/Agent/Storage | Архитектурные решения и границы модулей. |
| [docs/DATA_SOURCES.md](../docs/DATA_SOURCES.md) | У2 · Geo/Data | Источники, даты, метод геовычислений и ограничения качества. |
| [docs/FEATURE_REGISTRY.md](../docs/FEATURE_REGISTRY.md) | У3 · Backend/Agent/Storage | Форматы признаков и рабочий способ расширения. |
| [docs/ML_GUIDE.md](../docs/ML_GUIDE.md) | У1 · ML | Учебный разбор блоков ML и одного запроса по шагам. |
| [docs/PIPELINE.md](../docs/PIPELINE.md) | У3 · Backend/Agent/Storage | Сквозной путь запроса, ingestion и подтверждение отельера. |
| [docs/PROJECT_STRUCTURE.md](../docs/PROJECT_STRUCTURE.md) | У3 · Backend/Agent/Storage | Этот полный список файлов с назначением и владельцем. |
| [docs/REPO_AUDIT.md](../docs/REPO_AUDIT.md) | У3 · Backend/Agent/Storage | Первоначальный аудит реального upstream и карта переносов. |
| [docs/TASKS.md](../docs/TASKS.md) | У3 · Backend/Agent/Storage | Пять требований, реальные статусы, приоритеты и критерии TODO. |
| [docs/VALIDATION.md](../docs/VALIDATION.md) | У3 · Backend/Agent/Storage | Фактические запуски, результаты и непроверенные свойства. |
| [docs/examples/parse_response.json](../docs/examples/parse_response.json) | У3 · Backend/Agent/Storage | Ответ API parse-query на первый демонстрационный запрос. |
| [docs/examples/pytest_results.xml](../docs/examples/pytest_results.xml) | У3 · Backend/Agent/Storage | Машинный отчёт выполненного pytest. |
| [docs/examples/search_response.json](../docs/examples/search_response.json) | У3 · Backend/Agent/Storage | Полный ответ поиска с evidence на чистой seed-базе. |
| [docs/inputs/HACKATHON_TASK.txt](../docs/inputs/HACKATHON_TASK.txt) | У3 · Backend/Agent/Storage | Неизменённое входное ТЗ/материал пользователя; хранение, не статус реализации. |
| [docs/inputs/ostrovok_adler_blueprint/ARCHITECTURE.md](../docs/inputs/ostrovok_adler_blueprint/ARCHITECTURE.md) | У3 · Backend/Agent/Storage | Неизменённое входное ТЗ/материал пользователя; хранение, не статус реализации. |
| [docs/inputs/ostrovok_adler_blueprint/CODE_SKETCH.md](../docs/inputs/ostrovok_adler_blueprint/CODE_SKETCH.md) | У3 · Backend/Agent/Storage | Неизменённое входное ТЗ/материал пользователя; хранение, не статус реализации. |
| [docs/inputs/ostrovok_adler_blueprint/PROMPT_CODING_AGENT.md](../docs/inputs/ostrovok_adler_blueprint/PROMPT_CODING_AGENT.md) | У3 · Backend/Agent/Storage | Неизменённое входное ТЗ/материал пользователя; хранение, не статус реализации. |
| [docs/inputs/ostrovok_adler_blueprint/START_HERE.md](../docs/inputs/ostrovok_adler_blueprint/START_HERE.md) | У3 · Backend/Agent/Storage | Неизменённое входное ТЗ/материал пользователя; хранение, не статус реализации. |
| [docs/inputs/ostrovok_adler_blueprint/TEAM_TASKS.md](../docs/inputs/ostrovok_adler_blueprint/TEAM_TASKS.md) | У3 · Backend/Agent/Storage | Неизменённое входное ТЗ/материал пользователя; хранение, не статус реализации. |
| [frontend/__init__.py](../frontend/__init__.py) | У4 · Frontend | Объявляет Python-пакет; отдельной бизнес-логики нет. |
| [frontend/api_client.py](../frontend/api_client.py) | У4 · Frontend | HTTP-клиент backend с явными ошибками. |
| [frontend/app.py](../frontend/app.py) | У4 · Frontend | Streamlit UI: подбор, объяснения, сравнение и подтверждение ответов отельера. |
| [frontend/map_view.py](../frontend/map_view.py) | У4 · Frontend | MapEngine: адаптация FeatureGroup/Marker/PolyLine из agent_tool_map (Maxim, MIT). |
| [legacy/README.md](../legacy/README.md) | У3 · Backend/Agent/Storage | Как читать сохранённый upstream и почему он отдельно от приложения. |
| [legacy/agent_tool_map_45ad71a.zip](../legacy/agent_tool_map_45ad71a.zip) | У3 · Backend/Agent/Storage | Неизменённые исходные файлы upstream без .git. |
| [pyproject.toml](../pyproject.toml) | У3 · Backend/Agent/Storage | Python-пакет, зависимости, optional extras и конфигурация pytest. |
| [requirements.lock](../requirements.lock) | У3 · Backend/Agent/Storage | Точные версии установленной среды. |
| [scripts/__init__.py](../scripts/__init__.py) | У3 · Backend/Agent/Storage | Объявляет Python-пакет; отдельной бизнес-логики нет. |
| [scripts/collect_adler_osm.py](../scripts/collect_adler_osm.py) | У2 · Geo/Data | Online-команда. Не вызывается сервером; повторный запуск использует snapshot. |
| [scripts/compute_geo_features.py](../scripts/compute_geo_features.py) | У2 · Geo/Data | Вычисляет Geo-наблюдения из snapshot и записывает features.json. |
| [scripts/evaluate_parser.py](../scripts/evaluate_parser.py) | У1 · ML | Измеряем качество понимания запросов на заранее размеченном наборе. |
| [scripts/package_demo.py](../scripts/package_demo.py) | У3 · Backend/Agent/Storage | Собирает переносимый исходный проект с данными, без среды, секретов и рабочей БД. |
| [scripts/seed_demo.py](../scripts/seed_demo.py) | У3 · Backend/Agent/Storage | Повторный seed не удаляет ответы отельера и не дублирует наблюдения. |
| [scripts/validate_data.py](../scripts/validate_data.py) | У2 · Geo/Data | Проверяет реальные IDs, snapshot, checksum графа и воспроизводимость всех Geo-значений. |
| [tests/conftest.py](../tests/conftest.py) | У3 · Backend/Agent/Storage | Изоляция SQLite/сети, фиксированные часы TTL и общие fixtures. |
| [tests/test_api_smoke.py](../tests/test_api_smoke.py) | У3 · Backend/Agent/Storage | Сквозной API, ошибки, симуляция, конфликт и повтор seed. |
| [tests/test_conflicts.py](../tests/test_conflicts.py) | У3 · Backend/Agent/Storage | Версии, конфликты, будущие/устаревшие и simulated свидетельства. |
| [tests/test_evaluation.py](../tests/test_evaluation.py) | У1 · ML | Ошибки операторов, знаменатель метрик при сбое и типы отрицаний. |
| [tests/test_feature_agent.py](../tests/test_feature_agent.py) | У3 · Backend/Agent/Storage | Выбор инструмента, бюджет, вычисления и расширение YAML. |
| [tests/test_frontend.py](../tests/test_frontend.py) | У4 · Frontend | Экранирование внешнего текста на карте. |
| [tests/test_geo_routes.py](../tests/test_geo_routes.py) | У2 · Geo/Data | Обходы, no path, private/access, барьеры и ошибки источника. |
| [tests/test_hotelier.py](../tests/test_hotelier.py) | У3 · Backend/Agent/Storage | Номера/отрицания, неоднозначность и подтверждение. |
| [tests/test_query_parser.py](../tests/test_query_parser.py) | У1 · ML | Контракты, gold, единицы, отрицания и адаптер Ollama. |
| [tests/test_ranking.py](../tests/test_ranking.py) | У1 · ML | Строгие условия, веса, unknown и соответствие в одном номере. |
| [tests/test_streamlit_flow.py](../tests/test_streamlit_flow.py) | У4 · Frontend | UI AppTest → API: поиск, веса, ответ и подтверждение. |

## Локальные и генерируемые каталоги

- `.venv/` — установленная Python-среда; У3, создаётся командой README, не переносится в архив.
- `runtime/adler.db` — рабочая SQLite; У3, вопросы/ответы текущего запуска, не часть исходной поставки.
- `upstream/agent_tool_map/` — отдельный Git-клон оригинала commit `45ad71a637f1c7bbf561934326cbd8854f27f118`;
  У3 хранит для сравнения. Автор оригинальных файлов — Maxim; архив есть в `legacy/`.
- `artifacts/ostrovok-adler-mvp.zip` и `.zip.sha256` — пакет передачи, У3; создаются `scripts.package_demo`.
- `__pycache__/`, `.pytest_cache/`, `*.egg-info/` — служебные артефакты Python; не редактировать вручную.

План работ и границы DONE — [TASKS](TASKS.md). Учебный путь У1 — [ML_GUIDE](ML_GUIDE.md).
