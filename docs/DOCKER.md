# Запуск через Docker Compose

Нужен запущенный Docker Engine с Compose. Из корня проекта:

```bash
docker compose up --build --detach --wait
```

Frontend: <http://localhost:8501>. API/Swagger: <http://localhost:8000/docs>.
Готовность: <http://localhost:8000/api/health>.

Сервисы `backend` и `frontend` собираются из одного Dockerfile и работают
от пользователя `adler`. Backend сначала выполняет `scripts.migrate_db`
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
docker compose logs --follow backend frontend
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

Без `.env` работают те же заглушки, что и при локальном запуске:
`PARSER_MODE=fixture`, `REPLY_PARSER_MODE=rules`. Docker не меняет контракты
или распределение логики между backend и ML-слоем.

При необходимости скопируйте `.env.example` в `.env`. Compose передаёт
выбранные настройки и ключи только backend; `.env` не попадает в образ.
`DATABASE_URL` и `API_URL` из хостового `.env` не переопределяют контейнерные
пути и адрес сервиса — они явно заданы в `compose.yaml`.

| Переменная | Значение по умолчанию | Назначение |
|---|---|---|
| `BACKEND_PORT` | `8000` | Порт API на localhost хоста |
| `FRONTEND_PORT` | `8501` | Порт Streamlit на localhost хоста |
| `PARSER_MODE` | `fixture` | Гостевой parser: fixture/ollama/groq |
| `REPLY_PARSER_MODE` | `rules` | Ответ отельера: rules/fixture/ollama/groq |
| `DOCKER_OLLAMA_URL` | `http://host.docker.internal:11434` | Доступный из контейнера адрес Ollama |
| `MODEL_NAME` | `gemma3:12b` | Имя локальной модели |
| `GROQ_API_KEY` | пусто | Ключ облачного провайдера |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Имя облачной модели |

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
