# Запуск через Docker Compose

Нужен запущенный Docker Engine с Compose. Из корня проекта:

```bash
docker compose up --build --detach --wait
```

React: <http://localhost:8080>.
API/Swagger: <http://localhost:8000/docs>. Готовность: <http://localhost:8000/api/health>.

Сервис `backend` собирается из `Dockerfile` и работает от пользователя `app`.
Он сначала выполняет `scripts.migrate_db` и идемпотентный `scripts.seed_demo`,
затем запускает uvicorn. `web` (React + nginx, `web/Dockerfile`) обращается к
`http://backend:8000` по внутренней сети и ждёт healthcheck backend —
[порядок запуска Compose](https://docs.docker.com/compose/how-tos/startup-order/).
Образы работают на архитектуре хоста, включая Apple Silicon; отдельная
эмуляция amd64 не задаётся.

## Данные и остановка

SQLite и резервные копии находятся в именованном volume `adler-data`
(имя Docker содержит также префикс проекта Compose). Хостовая
`runtime/adler.db` не подключается и не перезаписывается. После остановки,
перезапуска или пересоздания контейнеров данные сохраняются:

```bash
docker compose logs --follow backend web
docker compose ps
docker compose down
docker compose up --detach --wait
```

Чтобы загрузить уже сохранённые отчёты среды с их учебными/оценочными метками:

```bash
docker compose exec backend python -m scripts.seed_demo --environment
```

Для полного сброса именно контейнерной демо-базы используется
`docker compose down --volumes`: эта команда удаляет volume и его историю.
Обычный `down` том не удаляет.

## Настройки ML

Без `.env` используются режимы из `config/models.yaml`: гостевой hybrid (правила + Gemma3 12B через Ollama; без Ollama — только правила), ответ отельера rules. Для работы без модели явно задайте `PARSER_MODE=offline` (правила) или `fixture` (готовые примеры). Docker не меняет контракты
или распределение логики между backend и ML-слоем.

При необходимости скопируйте `.env.example` в `.env`. Compose передаёт
выбранные настройки и ключи только backend; `.env` не попадает в образ.
`DATABASE_URL` и `API_URL` из хостового `.env` не переопределяют контейнерные
пути и адрес сервиса — они явно заданы в `compose.yaml`.

| Переменная | Значение по умолчанию | Назначение |
|---|---|---|
| `BACKEND_PORT` | `8000` | Порт API на localhost хоста |
| `PARSER_MODE` | из YAML | Операционное переопределение: hybrid/offline/fixture/ollama/groq |
| `REPLY_PARSER_MODE` | `rules` | Ответ отельера: rules/fixture/ollama/groq |
| `DOCKER_OLLAMA_URL` | `http://host.docker.internal:11434` | Доступный из контейнера адрес Ollama |
| `GROQ_API_KEY` | пусто | Ключ облачного провайдера |

Для Ollama на хосте задайте `PARSER_MODE=ollama` и/или
`REPLY_PARSER_MODE=ollama`. `localhost` внутри контейнера означает сам контейнер;
используется [host.docker.internal/host-gateway](https://docs.docker.com/compose/how-tos/networking/).
Ollama должна слушать адрес, доступный контейнеру; если она работает на другой
машине или в отдельном сервисе, задайте `DOCKER_OLLAMA_URL` явно.
Автоматического скачивания/запуска ML-модели в этом Compose нет.

Для Groq задайте соответствующий режим `groq` и ключ, затем пересоздайте
сервисы командой `docker compose up --detach --wait`. Изменения исходников
требуют `--build`. Ошибка ML не подменяется демо-ответом.

Сборка требует сети для базового образа и Python-зависимостей. Сам демо-поиск
после сборки использует данные из образа; `.venv`, рабочие БД, `.git`,
артефакты и секреты исключены из build context через `.dockerignore`.

## Проверка

29.10.2026 образы действительно собраны и запущены на Linux ARM64 в Docker Desktop.
Проверены healthcheck обоих сервисов, frontend → API по внутреннему DNS,
исходный поиск 12/2/11, pending → подтверждение → поиск номера и исключение
симуляции из обычной выдачи. После `down` и повторного `up` миграция/seed
сохранили ответ в volume и создали резервную копию. Контейнеры работают с
UID 10001; `pip check`, целостность SQLite и контроль хостовой БД прошли.
Изолированный тестовый проект и его volume удалены после проверки.
Регрессия: **188 passed, 1 skipped** (внешний NoiseModelling).
[Фактический отчёт](examples/docker_compose_validation.json).

Имена моделей, контекст, температура, таймаут и лимит ответа находятся только в
`config/models.yaml`; меняйте их там, затем пересобирайте образ.

Вариант запуска один — корневой `compose.yaml` (`docker compose up --build`): `backend` (8000),
`web` — React (8080, проксирует `/api`, `/docs`, `/openapi.json`, `/health` в backend).
Streamlit (`frontend/`, :8501) удалён 29.10.2026. Прежние `docker-compose.yml` + `docker-compose.web.yml` и `deploy/nginx.conf`
удалены при привязке фронтенда к `development/adler-mvp`: они поднимали второй проект Compose со своим
volume и путали сервисы (`api/ui/app/web` против `backend/frontend`).
