# Запуск через Docker Compose

Нужен запущенный Docker Engine с Compose. Из корня проекта:

```bash
docker compose up --build --detach --wait
```

React-интерфейс: <http://localhost:8080>. Streamlit: <http://localhost:8501>.
API/Swagger: <http://localhost:8000/docs> (и <http://localhost:8080/docs> через прокси web).
Готовность: <http://localhost:8000/api/health>.

| Сервис | Образ | Порт на хосте |
|---|---|---|
| `backend` | `Dockerfile` (FastAPI) | `127.0.0.1:8000` (`BACKEND_PORT`) |
| `web` | `web/Dockerfile` (React + nginx, `/api` → backend) | `127.0.0.1:8080` (`WEB_PORT`) |
| `frontend` | `Dockerfile` (Streamlit) | `127.0.0.1:8501` (`FRONTEND_PORT`) |

Сервисы `backend` и `frontend` собираются из одного Dockerfile и работают
от пользователя `app` (UID 10001). `web` — nginx-unprivileged со статикой React,
собранной в режиме `VITE_DATA_MODE=api`; он тоже ждёт healthcheck backend. Backend сначала выполняет `scripts.migrate_db`
и идемпотентный `scripts.seed_demo`, затем запускает uvicorn.
Frontend запускает текущий Streamlit и обращается к `http://backend:8000`
по внутренней сети. Он ждёт healthcheck backend —
[порядок запуска Compose](https://docs.docker.com/compose/how-tos/startup-order/).
Образы работают на архитектуре хоста, включая Apple Silicon; отдельная
эмуляция amd64 не задаётся.

## Данные и остановка

SQLite и резервные копии находятся в именованном volume `adler-data`
(имя Docker содержит также префикс проекта Compose). Хостовая
`runtime/adler.db` не подключается и не перезаписывается. После остановки,
перезапуска или пересоздания контейнеров данные сохраняются:

```bash
docker compose logs --follow backend web frontend
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

## Настройки frontend и ML

Без `.env` разбор запроса работает правилами без LLM (`PARSER_MODE=offline`),
ответ отельера — `REPLY_PARSER_MODE=rules`. Docker не меняет контракты
или распределение логики между backend и ML-слоем.

При необходимости скопируйте `.env.example` в `.env`. Compose передаёт
выбранные настройки и ключи только backend; `.env` не попадает в образ.
`DATABASE_URL` и `API_URL` из хостового `.env` не переопределяют контейнерные
пути и адрес сервиса — они явно заданы в `compose.yaml`.

| Переменная | Значение по умолчанию | Назначение |
|---|---|---|
| `WEB_PORT` | `8080` | Порт React-интерфейса на localhost хоста |
| `BACKEND_PORT` | `8000` | Порт API на localhost хоста |
| `FRONTEND_PORT` | `8501` | Порт Streamlit на localhost хоста |
| `DOCKER_PARSER_MODE` | `offline` | Гостевой parser в контейнере: offline/fixture/ollama/groq |
| `REPLY_PARSER_MODE` | `rules` | Ответ отельера: rules/fixture/ollama/groq |
| `DOCKER_OLLAMA_URL` | `http://host.docker.internal:11434` | Доступный из контейнера адрес Ollama |
| `GROQ_API_KEY` | пусто | Ключ облачного провайдера |

Имена моделей и параметры генерации — в `config/models.yaml` (входит в образ;
после правки нужен `--build`).

Для Ollama на хосте задайте `DOCKER_PARSER_MODE=ollama` и/или
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

Слияние React-фронта и бэкенда (29.10.2026): см. раздел «Docker» в `web/README.md`.

29.10.2026 образы действительно собраны и запущены на Linux ARM64 в Docker Desktop.
Проверены healthcheck обоих сервисов, frontend → API по внутреннему DNS,
исходный поиск 12/2/11, pending → подтверждение → поиск номера и исключение
симуляции из обычной выдачи. После `down` и повторного `up` миграция/seed
сохранили ответ в volume и создали резервную копию. Контейнеры работают с
UID 10001; `pip check`, целостность SQLite и контроль хостовой БД прошли.
Изолированный тестовый проект и его volume удалены после проверки.
Регрессия: **188 passed, 1 skipped** (внешний NoiseModelling).
[Фактический отчёт](examples/docker_compose_validation.json).
