# Задачи команды и интерфейсы между модулями

> **Статус:** план задач, а не отчёт о реализации. Меняйте `TODO` на `DONE` **только после работы и проверки кода**. Базовый coding-agent промпт: `PROMPT_CODING_AGENT.md`; архитектура: `ARCHITECTURE.md`.

## Быстрое распределение ответственности

| Роль | Владеет файлами | Что сдаёт коллегам | Первый результат |
|---|---|---|---|
| **ML/NLP + ranking** | `app/ml/*`, `app/schemas/query.py`, `data/evaluation/*`, `tests/test_query_parser.py`, `tests/test_ranking.py` | `ParsedHotelQuery`, `rank_hotels()` и gold JSON-тесты | Русский запрос → валидированный JSON со строгими и мягкими условиями |
| **Geo/Data** | `app/geo/*`, `scripts/collect_adler_osm.py`, `scripts/compute_geo_features.py`, `data/demo/osm*`, `tests/test_geo_routes.py` | OSM IDs, пешее расстояние с методом и source/provenance, quality flags | 15–30 реальных отелей выбранного участка; реальные маршруты до пляжа хотя бы для части |
| **Backend/Agent** | `app/api/*`, `app/agent/*`, `app/storage/*`, `app/features/*`, `app/hotelier/*`, `app/main.py`, `scripts/seed_demo.py` | REST API, source planner, сохранение evidence/conflict, hotelier workflow | `POST /api/search` на фиксированных демо-данных и вопрос отельеру |
| **Frontend/UI** | `frontend/*`, UX-часть `docs/API.md`, frontend-тесты | Поиск, слайдеры, результаты, источник, карточки, имитация отельера | UI с мок-ответом API, позже подключение backend |
| **QA/Integration** (может совмещаться) | `tests/test_api_smoke.py`, `docs/*`, `README.md`, `.env.example` | Проверенный запуск и демонстрация без онлайн загрузки | `pytest`, проверка установки по README, demo script |

Если команда меньше четырёх человек, роли совмещаются, а границы модулей сохраняются.

## Что уже имеется в open-source репозитории (подлежит аудиту)

- `demo.py`: LLM analysis query → JSON, OSM POI search, scoring, HTML-map.
- `engines/agent_engine/engine.py`: Ollama client, MapAgent с последовательным обработчиком запросов.
- `engines/map_search_engine/engine.py`: Overpass, геодезические расстояния, кеш/повторы.
- `engines/map_viz_engine/engine.py`: Folium карта.
- `config.py`: параметры, включая `gemma3:12b`.

Критическая правка: `profile='foot'` в оригинальном distance matrix **не считает пешеходный путь**, а только делит geodesic на скорость. Нужна новая Geo-реализация. На исходном GitHub нет готового BIO-обучения, cosine-similarity, полного процесса отельера и достоверности, соответствующей ТЗ.

## P0 — всем параллельно

### ML/NLP (ответственный: ML-участник)

- [ ] Создать `app/schemas/query.py`: `ParsedHotelQuery`, `HardConstraint`, `SoftPreference`, валидируемые операторы, единицы, допустимые `feature_key` и scope.
- [ ] В `app/ml/prompts.py` зафиксировать few-shot русские примеры с JSON. Обязательно: «не дальше 500 м», «не рядом с барами», «недалеко» без придуманного числа, «номер с видом» (scope room), «тишина важнее вида».
- [ ] Создать `app/ml/query_parser.py`: Ollama structured JSON + `Pydantic`, normalizer метры/км, отказ на неизвестный feature; `PARSER_MODE=fixture` для запуска без LLM.
- [ ] Создать `app/ml/ranking.py`: подтверждённые hard-нарушения исключить, unknown отдельно, мягкие условия в weighted score, evidence-based explanation; не считать unknown как успешный match.
- [ ] Создать `data/evaluation/queries_gold.jsonl` (40–60 вручную проверенных случаев) и `scripts/evaluate_parser.py`; тесты с контролируемой моделью или fixture. Метрики публиковать только после реального запуска.

**Передать backend:** Pydantic-контракты + примеры JSON. **Передать frontend:** формат preferences и правила редактирования весов. Не писать геоалгоритмы и DB queries внутри ML-модуля.

### Geo/Data (ответственный: GIS/data-участник)

- [ ] Через Overpass/OSM проверить **конкретную** прибрежную область Адлера: есть ли 15–30 настоящих отелей, пляжи и пешеходные пути; координаты и bbox сохранить в конфиге с датой.
- [ ] Создать `scripts/collect_adler_osm.py` для идемпотентной выгрузки реальных OSM POI: hotel, beach + beach access, дороги/пешеходные пути, железная дорога, bars/nightclubs.
- [ ] Создать `app/geo/routing.py`: `get_pedestrian_distance()` через OSMnx/NetworkX, возврат distance/units/method/source/quality; fallback должен быть `unknown`, а не geodesic как «пешком».
- [ ] Отдельно геодезический prefilter, если нужен, но показывать его пользователю только как «по прямой».
- [ ] Создать `scripts/compute_geo_features.py`: предвычислить маршруты и сохранить `data/demo/features.*` + provenance и дату. Не вызывать внешние API на каждом search.
- [ ] Тесты: искусственный обход препятствия, no-path, плохая разметка, невозможность пройти к входу пляжа.
- [ ] (P1) `app/geo/quietness.py`: noise proxy на основе OSM, документированные допущения, без заявлений о децибелах.

**Передать backend:** DTO `FeatureObservation` для каждого отеля, файлы данных, `source_ref` и quality flags. **Передать frontend:** линии маршрутов/GeoJSON для карты, если есть.

### Backend/Agent (ответственный: backend-разработчик)

- [ ] Создать `app/storage/models.py`: Hotel, optional Room, FeatureDefinition, FeatureObservation, Evidence, Source, Conflict, HotelierQuestion/Answer.
- [ ] Создать `app/features/registry.yaml` и загрузчик. Неизвестный feature → unknown/unsupported, а не воображаемый результат.
- [ ] `app/agent/tool_registry.py`: типизированные именованные инструменты только из whitelist, retry/timeout/error + `tool_used` в trace.
- [ ] `app/agent/feature_agent.py`: план по feature → существующее значение / geo tool / hotelier question, запись source/date; документировать, где есть реальный выбор инструмента, а где rules engine.
- [ ] `app/features/service.py`: конфликт на тот же subject+feature+time, stale, статус, provenance. Не перетирать источник ответом отельера.
- [ ] `app/hotelier/dialogue.py`: вопрос → свободный текст → Pydantic extracted room fact → human confirmation → persistent value + evidence. Демонстрационное высказывание не выдавать за правду о реальном отеле.
- [ ] `app/api/*`, `app/main.py`: `/health`, `/parse-query`, `/search`, `/hotels`, `/evidence`, `/hotelier/questions`, `/answer`, `/confirm`; docs OpenAPI.
- [ ] `scripts/seed_demo.py`: быстро заполнить SQLite из сохранённых data fixtures; online data pipeline отдельный.

**Передать frontend:** точные API-схемы и статусы ошибок. **Передать ML:** функция чтения характеристик с типами и known/unknown/estimated.

### Frontend (ответственный: frontend-разработчик)

- [ ] `frontend/api_client.py`: только HTTP к FastAPI, typed payload/error handling, никаких импортов `app.storage` или sqlite.
- [ ] `frontend/app.py` Streamlit: текстовый поиск, вид распознанных пожеланий, редактируемые веса, кнопка поиска.
- [ ] Карточка: расстояние с методом («пешком по данным OSM»), source, дата, `estimated/unknown`, объяснение. Не показывать invented рейтинги/звёзды/цены.
- [ ] Карта реальных отелей, при наличии — полилиния пешеходного маршрута, сравнение 2–3 объектов.
- [ ] Вкладка «Отельер (демо)»: вопрос, свободный ответ, предварительное извлечение, подтверждение.
- [ ] Старт сначала с API stub/mock fixtures, затем совместная проверка с backend.

**Передать QA:** кликабельный end-to-end сценарий и нужные команды запуска.

## P1 — после вертикального сценария

- [ ] Экран явных конфликтов/устаревших фактов.
- [ ] Room-level features, условие «только в номерах с 3-го этажа».
- [ ] `quietness_proxy` с описанием допущений + карта факторов.
- [ ] Покрытие и точность на размеченном gold-наборе.
- [ ] Дополнительный открытый API, если отвечает реальной потребности (погода Open-Meteo, история Wikidata, работающие ночью места — OSM `opening_hours`).
- [ ] Улучшить explanation и сравнение.

## P2 — необязательное (не блокировать MVP)

- [ ] Геометрический расчёт `sunset_view` на основе DEM, высот зданий и ориентации фасада, лишь при достаточных источниках.
- [ ] Cosine/embedding поиск по описаниям и ответам отельера.
- [ ] Реальный кабинет отельера с безопасной авторизацией.
- [ ] Планировщик обновления TTL и уведомления об изменениях.
- [ ] Замена Streamlit на React, если UX-выигрыш очевиден и есть время.

## Интеграционный контракт: не ломать соседние компоненты

1. **ML → Backend**: только `ParsedHotelQuery` по схеме `app/schemas/query.py`.
2. **Geo → Backend**: `FeatureObservation` c `source`, `method`, `collected_at`, `quality_flags`, `status`; ни слова про «истинный вид из окна» из OSM без доказательства.
3. **Backend → Frontend**: JSON API, где unknown/conflicted — отдельные состояния, а не `false`.
4. **Frontend → ML**: пользователь меняет веса; backend пересчитывает ranking и не меняет сами наблюдения.
5. **Agent → Tools**: только whitelist, понятные ошибки и лог исполнения.

## Требования к Pull Request любого участника

- Описание цели, затронутых файлов и изменений API.
- Пример входа/выхода функции и тест (в идеале pytest).
- Указание источников для геоданных и прав на исходный код.
- Изменение `docs/PROJECT_STRUCTURE.md`, если появились новые файлы.
- Никаких коммитов `.env`, ключей, огромных выгрузок или выдуманных фактов.

## Что команда должна продемонстрировать жюри

- [ ] 1) Текст на русском → адекватный валидный JSON.
- [ ] 2) В карточке отеля есть **вычисленная**, а не скопированная из текста геохарактеристика.
- [ ] 3) Показаны источник, дата, метод, ограничения и статус уверенности.
- [ ] 4) Вопрос отельеру, свободный ответ, confirmation, повторный поиск с новым фактом.
- [ ] 5) Персонализированное ранжирование + объяснение + хотя бы простое сравнение.
- [ ] 6) Проект стартует локально с заранее подготовленными данными по README.

**Необязательная красота интерфейса и число парсеров менее важны, чем честное получение новых характеристик.**
