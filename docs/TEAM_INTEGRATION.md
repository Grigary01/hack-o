# Интеграция веток · 29 октября 2026

Ветка `integration/mvp` сводит в одну работающую версию:

| Источник | Что принесла |
|---|---|
| `development/adler-mvp` (= `main`, `geo/viewshed`) | Geo: маршруты от контура здания, тихая сторона по фасадам, облегчённый поиск |
| `ml/hybrid-parser` | Гибридный разбор запроса, промпт с `query_hint`, наборы оценки v2/v3 |
| `grisha_hack` | Backend: миграции Alembic, жизненный цикл вопросов отельеру, разбор ответов, конфликты, Docker Compose |
| `frontend/mvp` | React-интерфейс `web/`, сервис `web` в `compose.yaml` |

## Как запускать

```bash
# Backend + React + Streamlit
docker compose up --build
# React: http://localhost:8080, Streamlit: http://localhost:8501, API: http://localhost:8000/docs
```

Без Docker: backend по README, затем в `web/` — `npm ci && npm run dev:api`
(`http://localhost:5173`). `npm run dev:mock` — демонстрационные данные, не Адлер.

## Разрешённые конфликты и правки при слиянии

- `config/models.yaml`, `app/core/*`: сохранены оба нововведения — `parser_mode: hybrid`
  с `hybrid_llm` и отдельный `reply_parser_mode` для ответов отельера.
- `app/ml/query_parser.py`: защита от выдуманных чисел совмещена с новыми ошибками
  недоступности Ollama/Groq (`QueryParserUnavailable`). Гибрид при недоступной LLM
  возвращает разбор правил, а не HTTP 502.
- `app/ml/prompts.py`: LLM видит все признаки, которые гость может запросить
  (есть `query_hint` или `query_patterns`, либо `provider: hotelier`). Поэтому
  признак, добавленный только в YAML (`blackout_curtains`), сразу доступен модели.
  Скрыты лишь расчётные спутники (`*_potential`, `*_min_floor`, `aircraft_noise_exposure`).
- `.dockerignore`: белый список backend + добавлен `config/` (Dockerfile копирует его,
  без этого сборка образа падала); `web/` и `frontend/design` исключены из backend-образа.
- React API-слой переведён на `GET /api/hotels/{id}/evidence` (текущее знание с учётом
  TTL и конфликтов); проверки `scripts/verify_backend.py` больше не зашивают число
  отелей и признаков.

## Привязка frontend/mvp (29 октября, после интеграции)

- Бэкенд, тесты, данные и docs взяты из `development/adler-mvp` без изменений, кроме
  `blackout_curtains` в реестре: алиас «blackout» и шаблон «шторы blackout» — иначе ответ
  «В номерах 301–305 есть шторы blackout» не разбирается, а «шторами» уходит в «не учтено».
- Docker: один `compose.yaml` с сервисами `backend`, `web` (React, :8080) и `frontend` (Streamlit, :8501);
  `docker-compose.yml`, `docker-compose.web.yml`, `deploy/nginx.conf` удалены.
- React: `GET /api/hotelier/answers/{id}`, фильтры `GET /api/hotelier/questions?hotel_id=&status=`,
  `context` вопроса (почему открыт, ссылка «Вернуться к проверке»), ошибки `{code, detail}`
  (409 — «состояние изменилось»), текущее знание из `/evidence` сохранено.

## Проверки

- `python -m pytest`: 296 passed, 1 skipped.
- `web/`: `npm run build` и `npm test` (vitest) проходят.

## Качество разбора запросов (requirement F1, gemma3:12b)

| | dev v2 (59) | тест v3 (60) |
|---|---|---|
| Gemma, промпт до правок | 0.779 | 0.771 |
| Только правила | 0.847 | 0.865 |
| Hybrid | 0.864 | 0.886 |

Разметка синтетическая (coding assistant, без человеческой проверки). Тест v3 частично
просмотрен при выборе стратегии слияния — для итоговой цифры нужен новый замороженный тест.
Как пересчитать: `python -m scripts.compare_parser --mode hybrid --dataset data/evaluation/parser_test_v3_2026-10-29.jsonl`.
