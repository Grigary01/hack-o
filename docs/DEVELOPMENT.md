# Разработка и внутренние заметки команды

Перенесено из корневого README 29.10.2026, когда README приведён к шаблону организаторов.
Запуск для жюри — в [README](../README.md). Порт 8000 бэкенда больше не публикуется на хост:
API доступен через `http://localhost:8080/api`, Swagger — `http://localhost:8080/docs`.

## Интеграция команды · 29 октября

Сведены Geo/main, backend `grisha_hack`, React `frontend/mvp` и локальные ML-правки.
[Изменения, роли, проверки и ограничения](TEAM_INTEGRATION.md).
Интерфейс — React в `web/` (Streamlit удалён 29.10). Всё поднимается одним `docker compose up --build`
(`docker-compose.yml`: backend + React).
Для подключения React к API без Docker: запустите backend, затем в `web/` выполните
`npm ci`, `npm run dev:api` и откройте `http://localhost:5173`.
`npm run dev:mock` — отдельный демонстрационный сценарий Батуми, не данные Адлера.

## Быстрый старт

```bash
git clone https://github.com/ostrovok-hackathon-2026/cu5people.git
cd cu5people
cp .env.example .env   # необязательно: порты, адрес Ollama, ключи; модель — в config/models.yaml
docker compose up --build
# React: http://localhost:8080   API/Swagger: http://localhost:8080/docs
```

Первая сборка — несколько минут (образы, Python-колёса, npm). Демо-данные уже лежат
в репозитории, загрузка OSM/DEM при старте не выполняется. Остановка: `Ctrl+C` или `docker compose down`;
`docker compose down -v` дополнительно удалит базу с ответами отельера.

Режим разбора запроса берётся из `config/models.yaml` (`hybrid`: правила + LLM на непонятом).
Без Ollama гибрид возвращает разбор правил; чтобы LLM не вызывалась вовсе, задайте `PARSER_MODE=offline`
в `.env`. Для LLM: `ollama pull gemma3:12b` на хосте (адрес — `DOCKER_OLLAMA_URL`).
Облачный Claude (`claude-opus-5`) вместо локальной модели: в `.env` задайте `PARSER_MODE=groq`,
`CLOUD_LLM_BASE_URL`, `CLOUD_LLM_MODEL` и ключ в `GROQ_API_KEY` — compose передаёт их в `backend`;
подробно и с замерами — [CLAUDE_PARSER](CLAUDE_PARSER.md). Ключ только в `.env`, не в Git и не в образе.

## Зависимости и переменные окружения

Ресурсы без inference: 2 CPU, 2 GB RAM, ~2.5 GB диска под образы.
Ollama работает отдельно: веса Gemma 12B занимают около 8.2 GB, память нужна дополнительно.

Сервисы в [`docker-compose.yml`](../docker-compose.yml); наружу публикуется только `WEB_PORT` (8080):

| Сервис | Порт | Что это |
|---|---|---|
| `web` | **8080** (`WEB_PORT`) | React-фронт из `web/` (nginx); `/api/*`, `/docs`, `/openapi.json`, `/health` проксируются в `backend` |
| `backend` | 8000 (только внутри сети compose) | FastAPI; `docker/backend-entrypoint.sh`: миграции Alembic с резервной копией → идемпотентный seed → uvicorn |

`backend` собирается из `Dockerfile` (multi-stage, пользователь без root);
`web` собирается из `web/Dockerfile` в режиме `VITE_DATA_MODE=api`. База — SQLite в томе `adler-data`
(`/app/runtime/adler.db`, бэкапы в `/app/runtime/backups`). Порядок: `backend` healthy → `web`.

Общие ML-настройки команды лежат в [`config/models.yaml`](../config/models.yaml):
режим, имена моделей, температура, контекст, лимит ответа, таймаут.
Веса скачиваются отдельно и не входят в Git/образ Docker.
Подробности и роли участников: [настройка модели](MODEL_CONFIGURATION.md), [DOCKER](DOCKER.md).

В `.env.example` — только окружение и секреты: порты, `PARSER_MODE`/`REPLY_PARSER_MODE`
(пусто — из YAML), `DOCKER_OLLAMA_URL` (по умолчанию `http://host.docker.internal:11434`),
пустые места для `GROQ_API_KEY`/`OPENAQ_API_KEY`. Свой `.env` не коммитьте.
Ollama не открывайте в публичный интернет. Скрытого переключения на выдуманные фильтры нет.

## Сидирование

Выполняется автоматически при старте `backend` (после миграций; идемпотентно: ответы отельера
не стираются, дубликатов нет). Вручную:

```bash
docker compose exec backend python -m scripts.seed_demo
```

Демо-данные — `data/demo/` (отели, маршруты, 400 наблюдений) и `data/environment/` (здания, береговая линия,
рельеф Copernicus, ВПП). Пересбор из интернета (не нужен для демо) — раздел «Проверки и обновление данных».

## Маршруты/доступ

- `http://localhost:8080/` — React: поиск, выдача с картой, карточка отеля, кабинет отельера (`/hotelier`)
- `/health` — `200 OK`, JSON `{"status": "ok", "hotels": 25}` (`503 {"status": "needs_seed"}`, если база пуста)
- `/api/health`, `/api/search`, `/api/parse-query`, `/api/hotels`, `/api/hotels/{id}/evidence`,
  `/api/hotelier/...` — REST API, подробно в [docs/API.md](API.md)
- `/docs` — Swagger UI
- Авторизации нет: кабинет отельера — локальная демонстрация, тестовые учётные данные не нужны.

## О проекте

Обновление 26 октября: [NoiseModelling/OpenAQ и проверка Адлера](ENVIRONMENT.md),
[облачные модели и ранжирование v2](MODELS_AND_RANKING.md).
Для сохранённых отчётов среды: `python -m scripts.seed_demo --environment`.
Для облачной LLM нужен личный Groq Free Plan key; профили 20B/27B/120B ещё
**не сравнивались на реальной генерации**. Текущий общий режим — Ollama; офлайн-разбор доступен через `PARSER_MODE=offline`.
Акустика на реальной геометрии пока представляет явно помеченный учебный сценарий.

Актуальный проект расположен **в корне репозитория**. Запускайте backend через
`app.main:app`. Старая вложенная копия `Островок/` удалена при очистке 29.10.2026.
Корневой `main.py` содержит сохранённые учебные заглушки f/y и не используется при запуске.

Работающий локальный MVP: русский запрос → типизированные условия → выбор источника агентом →
пешие маршруты/шумовой proxy → подбор с объяснениями → диалог с демонстрационным отельером.

Подготовлены **25 реальных OSM-отелей** и **400 наблюдений** по 16 расчётным характеристикам из открытых данных — у каждого
источник, дата, срок годности, уверенность и человеческое объяснение. Полный реестр включает также 4 признака номеров, получаемых от отельера.

## Запуск через Docker Compose

```bash
docker compose up --build --detach --wait
```

React: <http://localhost:8080>, API/Swagger: <http://localhost:8080/docs>.
Миграции и seed выполняются автоматически; SQLite сохраняется в Docker volume.
Остановка: `docker compose down` — данные сохраняются.
Настройки ML, порты и команды: [DOCKER](DOCKER.md).

## Запуск без Docker

Проверено на macOS arm64, Python **3.12.7** (этапы backend) и **3.13.5** (исходное демо).
Используйте Python 3.12+.
Запускайте команды из корня проекта. При первой установке нужен интернет; для offline/fixture после установки — нет; Ollama требует запущенной локальной модели, Groq — сети.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements.lock -e '.[test]'
python -m scripts.migrate_db
python -m scripts.seed_demo
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Во втором терминале — React-интерфейс (нужен Node.js ≥ 20.19):

```bash
cd web
npm ci
npm run dev:api        # Vite проксирует /api на http://127.0.0.1:8000
```

Интерфейс: <http://localhost:5173>. Swagger: <http://127.0.0.1:8000/docs>.
API: <http://127.0.0.1:8000/api/health>. Оба процесса останавливаются `Ctrl+C`.
`seed_demo` идемпотентен: не удаляет ответы и не создаёт дубликаты. Файл SQLite: `runtime/adler.db`.
Чтобы начать новое демо, задайте другой `DATABASE_URL`, затем снова выполните seed; не удаляйте чужую базу.

`.env` не обязателен. При необходимости скопируйте `.env.example` в `.env`.
Ключи/API Островка не нужны. Карта — MapLibre с подложкой OpenFreeMap (нужна сеть в браузере);
без сети показывается SVG-схема по координатам. Фото в карточках — иллюстративные, с подписью «Фото для примера».

## Обновление SQLite и подключение участников

Перед обновлением существующей базы остановите backend и выполните
`python -m scripts.migrate_db`. Команда создаёт проверенную резервную копию
в `runtime/backups/`, проверяет известную схему и применяет миграции Alembic.
Повторный запуск сохраняет данные. Подробности: [MIGRATIONS](MIGRATIONS.md).

Решение конфликта уже доступно через API и учитывается поиском, агентом и evidence.
Для ML сохранены существующие форматы с необязательным контекстом конфликтов.
Примеры подключения: [CONFLICT_INTEGRATION](CONFLICT_INTEGRATION.md).
Экрана оператора в React пока нет: решение принимается через `POST /api/hotelier/conflicts/{id}/resolve`
(Swagger `/docs`). [Контракт API](API_FRONTEND_INTEGRATION.md).
Вопрос повторно открывается при конфликте или устаревании, сохраняя историю;
фильтры очереди и заглушки её состояний: [QUESTION_INTEGRATION](QUESTION_INTEGRATION.md).
Разбор ответа отельера заменяется отдельно от гостевого parser через
`REPLY_PARSER_MODE=rules|fixture|ollama|groq`. По умолчанию остаётся offline rules.
Контракт ML, режим заглушки и ошибки: [REPLY_PARSER_INTEGRATION](REPLY_PARSER_INTEGRATION.md).
Настоящая генерация ответов отельера на текущем окружении ещё не проверялась.

## Сценарий для жюри

Всё в React на <http://localhost:8080>.

1. На главной нажмите пример «Ищу тихий отель в Адлере, не дальше 500 метров пешком от пляжа, хотелось бы вид на море»
   и «Найти отели». Чипы показывают, как понят запрос; отели разбиты на «Условия подтверждены» и «Не все условия подтверждены».
2. «Источники» у карточки: OSM ID, дата, метод, уверенность, ограничения. К «вид на море» и «тихий» поиск сам добавил
   расчёт по геоданным — вид из окон здания («стороны ЮЗ, с 3-го этажа») и расстояние до траектории самолётов.
3. «Посмотреть номер» — карточка отеля: соответствие пожеланиям и «На чём основан подбор».
4. Запрос из макета: «Прилетаем поздно. Нужен номер со шторами blackout, магазин ночью и море пешком».
   У части отелей «Шторы blackout — нет данных» → «Запросить у отельера» → «Ответить за отельера (демо-кабинет)».
5. В кабинете: «Ответить» → «В номерах 301–305 есть шторы blackout. В номере 101 нет штор blackout.» → «Проверить данные».
   Разбор по номерам видно до публикации; до подтверждения факты не используются.
6. «Подтвердить и опубликовать» → «Характеристики обновлены», «Как увидит гость». «Открыть выдачу как гость» —
   отель теперь с «Шторы blackout — есть в номере 301».
7. Ответьте на тот же вопрос противоречиво («В номере 301 нет штор blackout»): вопрос снова откроется
   с причиной «Источники расходятся», обе версии останутся в истории. Решение оператора — в Swagger `/docs`:
   `GET /api/hotelier/conflicts`, затем `POST /api/hotelier/conflicts/{id}/resolve`.
8. Свой запрос, например «Тихий отель у моря без баров, подальше от самолётов, чтобы не переходить трассу».
   Слова, которые система не знает, показываются как «Не учтено».
9. Актуализация: `docker compose exec backend python -m scripts.refresh_geo --simulate-building 43.42503,39.91437,12`
   («построили» 12-этажный дом перед Cascade) → у Cascade и Golden Tennis Club закат «круглый год» станет
   «по сезонам», а «Черномор» потеряет единственный просвет на море с 4-го этажа.

Сценарий расширения «Нужен номер с плотными шторами» и подключение нового
свойства без ветвлений в агенте/хранилище/ранжировании: [этап 6](REGISTRY_EXTENSION.md).

Повторяемая приёмка на отдельной SQLite: `python -m scripts.verify_backend`.
Результаты, точки подключения frontend/ML и оставшиеся проверки:
[BACKEND_HANDOFF](BACKEND_HANDOFF.md).

Оценка 1.0 означает совпадение **известных мягких пожеланий**, а не «отель подходит на 100%».
Рядом всегда показывается покрытие, сортировка использует `score × coverage`.

## Парсер и границы готовности

По умолчанию `parser_mode: ollama` в `config/models.yaml`. Для разработки без LLM доступны `PARSER_MODE=offline` (правила) и `PARSER_MODE=fixture` (15 готовых примеров из `/api/demo-queries`).
Другие формулировки явно требуют уточнения. Это **не универсальный NLP-парсер**.

Общая модель и параметры задаются в `config/models.yaml`. В локальном `.env`
можно задать `OLLAMA_URL=http://127.0.0.1:11434` (адрес inference-сервера).
После `ollama pull gemma3:12b` и запуска Ollama перезапустите backend.
28 октября Gemma 12B проверена двумя реальными запросами: поиск 18.94 с и разбор
условия «не ближе 300 м» 5.85 с. Это smoke-проверка, не оценка качества на gold.
Ollama получает JSON Schema и 6 учебных примеров; ответ проверяется Pydantic.
Ошибки не заменяются выдуманными фильтрами.
См. [официальную документацию structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

Отельер использует ограниченный offline-парсер простых предложений: номера, диапазоны, булево свойство, отрицание, этаж.
Сезонность, исключения, «во всех номерах» без номеров требуют уточнения. Реальной авторизации/отправки сообщений нет.

## Проверки и обновление данных

```bash
python -m pytest
python -m scripts.validate_data
python -m scripts.evaluate_parser --mode offline
python -m scripts.evaluate_viewshed
# Только при доступной модели:
python -m scripts.evaluate_parser --mode ollama
```

Отдельная онлайн-подготовка (не нужна для демо):

```bash
python -m pip install -c requirements.lock -e '.[geo,test]'
python -m scripts.collect_adler_osm
# Для новой выгрузки вместо сохранённой: добавьте --refresh
python -m scripts.collect_environment_osm      # здания
python -m scripts.collect_viewshed_inputs      # береговая линия + рельеф Copernicus
python -m scripts.collect_aircraft_inputs      # ВПП аэропорта
python -m scripts.collect_amenities_osm        # заведения с opening_hours
python -m scripts.compute_geo_features
python -m scripts.validate_data
python -m scripts.seed_demo
```

Не запускайте сбор параллельно с записью тех же файлов. Обновление может изменить выборку и результаты поиска.
Сохранённые сведения имеют TTL; после его истечения они перестанут подтверждать условия. Повторный seed
не делает их свежими. Живой поиск не обращается к Overpass; агент сообщает о необходимости обновить snapshot
и даёт команду `python -m scripts.refresh_geo --refresh`: она сравнит здания, найдёт затронутые отели
и покажет «было → стало» (`--apply` записывает новый снимок; старые значения заменяются, а не конфликтуют).

## Разбор ML для начинающего разработчика

Начните с [ML_GUIDE](ML_GUIDE.md): порядок чтения файлов, роль каждого блока,
пример расчёта score/coverage, JSON Schema, few-shot и объяснение метрик. В `app/ml/`,
`app/schemas/query.py` и `scripts/evaluate_parser.py` добавлены подробные комментарии на русском.

## Где работать команде

```text
app/ml/        — участник 1: понимание запроса и ранжирование
app/geo/       — участник 2: источники, пешеходный граф и геовычисления
app/agent/     — участник 3: planner и whitelist инструментов
app/storage/   — участник 3: SQLite, версии и evidence
app/features/  — участник 3: реестр и достоверность
app/hotelier/  — участник 3: вопрос, разбор, подтверждение
app/api/       — участник 3: REST API
app/schemas/   — общий контракт участников 1–3
web/           — участник 4: React-интерфейс (Vite, TypeScript), mock- и api-режимы
scripts/       — ingestion, seed, проверка данных и метрики
data/demo/     — сохранённые реальные OSM-данные и отдельные parser fixtures
data/evaluation/— 44 синтетических запроса с ожидаемыми JSON, созданные coding assistant и фактические метрики
tests/         — проверки без внешней сети
docs/          — аудит, архитектура, API, ответственность и готовность
legacy/        — неизменённый архив исходного проекта с MIT LICENSE
```

Имена участников не переданы, поэтому закреплены роли 1–4. Полное дерево и владелец **каждого файла**:
[PROJECT_STRUCTURE](PROJECT_STRUCTURE.md). Готовность и задачи: [TASKS](TASKS.md).
Проверки: [VALIDATION](VALIDATION.md). Путь запроса: [PIPELINE](PIPELINE.md).
Реальные источники и ограничения: [DATA_SOURCES](DATA_SOURCES.md).
Контракты: [API](API.md), [FEATURE_REGISTRY](FEATURE_REGISTRY.md).

Основа — [agent_tool_map](https://github.com/MaximShalankin/agent_tool_map), Maxim, MIT.
Аудит и карта переносов: [REPO_AUDIT](REPO_AUDIT.md). Лицензии: [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md).
Для передачи проекта выполните `python -m scripts.package_demo`: появятся ZIP и SHA256 в `artifacts/`.
Архив содержит исходники, документацию и демо-данные; среда, секреты и рабочая база в него не включаются.

Исходные пять Markdown-файлов сохранены в `docs/inputs/`; это входное ТЗ, не отчёт о готовности.
