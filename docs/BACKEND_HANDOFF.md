# Backend: приёмка и передача

Дата: 29.10.2026. Ветка передачи: `grisha_hack`. Все изменения находятся
в корневом `hack-o`; старая вложенная `Островок/` удалена при очистке.
Исходные проверки выполнялись на основе ветки `grisha_back`.

Локальная часть этапа 7 выполнена: backend, текущий Streamlit и контракты
для замены frontend/ML проверены. Полная приёмка свободного текста остаётся
открытой: реальная LLM недоступна. Fixture и MockTransport не подтверждают
качество генерации.

## Что передаётся участникам

| Кому | Точка подключения | Инструкция |
|---|---|---|
| Frontend | HTTP API, OpenAPI, коды ошибок, обновление выдачи после сохранения | [API_FRONTEND_INTEGRATION](API_FRONTEND_INTEGRATION.md), [API](API.md) |
| Frontend: конфликты | `ConflictClient` и явный `ConflictStub` | [CONFLICT_INTEGRATION](CONFLICT_INTEGRATION.md) |
| Frontend: вопросы/ответы | `QuestionClient`, заглушка состояний, история и подтверждение | [QUESTION_INTEGRATION](QUESTION_INTEGRATION.md) |
| ML | `ReplyParser`, `ReplyExtraction`, адаптеры Ollama/Groq, валидация backend | [REPLY_PARSER_INTEGRATION](REPLY_PARSER_INTEGRATION.md) |
| Новые характеристики | YAML → динамические API/UI/промпты/схемы | [REGISTRY_EXTENSION](REGISTRY_EXTENSION.md), [FEATURE_REGISTRY](FEATURE_REGISTRY.md) |
| Существующая SQLite | Alembic 0001–0003, проверка схемы и резервная копия | [MIGRATIONS](MIGRATIONS.md) |

Заглушки подключаются явно; сбой реальной модели не подменяется fixture-ответом.
Модель разбирает пожелания и текст ответа; свойства отелей поступают из источников
и подтверждённых наблюдений. Симуляция остаётся `hotelier_simulated`, `estimated`,
`low`, с цитатой и TTL; обычный поиск её исключает.

## Повторяемая приёмка

После установки по [README](../README.md) из корня:

```bash
python -m pip check
python -m pytest -ra --junitxml=runtime/backend_pytest.xml
python -m scripts.verify_backend --output runtime/backend_acceptance.json
```

Команда `verify_backend` создаёт новую папку `runtime/backend-acceptance-*`,
применяет миграции, дважды выполняет seed и запускает uvicorn/Streamlit
на свободных портах localhost. Затем проходит настоящий интерфейс через AppTest,
повторяет миграцию/seed заполненной базы и перезапускает backend. Процессы
останавливаются при завершении, логи/БД остаются для проверки. Рабочая база
`runtime/adler.db` не изменяется. Требуется возможность слушать localhost.
LLM и внешние API для этого сценария не нужны; AppTest не заменяет визуальный QA.

`python -m scripts.validate_data` отдельно воспроизводит все геонаблюдения;
команда перезаписывает `data/demo/quality_report.json`. Для приёмки этапа 7
новый отчёт сохранён отдельно, исторический файл восстановлен.

## Результаты этапа 7

- Полный pytest: **188 passed, 1 skipped**. Пропущен внешний NoiseModelling,
  который в этой среде не настроен. Есть предупреждение Starlette о будущем
  изменении зависимости TestClient/httpx. [JUnit](examples/backend_stage7_pytest.xml).
- Все 75 геонаблюдений воспроизведены, checksum графа совпал;
  25 отелей, 23 вычисленных маршрута.
  [Проверка данных](examples/backend_stage7_data_validation.json).
- Настоящие серверы uvicorn и Streamlit проходят health. Исходный геопоиск
  возвращает 12 `matched`, 2 `needs_verification`, 11 `excluded`.
- Сценарий «Плотные шторы» через текущий UI: 0 подходящих → pending 0 →
  подтверждение 1 → противоречие 0 → явное решение 1. Выбор версии и причина
  обязательны, после сохранения выдача обновляется автоматически.
- Оба метода ранжирования выбирают номер 501; повторное подтверждение/решение
  идемпотентно, несовместимое решение даёт 409. Обе версии и исходные цитаты
  остаются в evidence. После миграции, повторного seed и перезапуска история
  и результат сохраняются; `integrity_check`/`foreign_key_check` пройдены.
  [Сквозной отчёт](examples/backend_stage7_flow.json).
- Отдельно распакован исходный ZIP, создана новая `.venv` без system-site-packages,
  выполнена установка `-c requirements.lock -e '.[test]'` на Python 3.12.7.
  `pip check` прошёл, все 58 установленных пакетов, перечисленных в constraints,
  совпали с закреплёнными версиями. Полный pytest и тот же настоящий HTTP/UI-сценарий
  прошли из распакованной копии: **188 passed, 1 skipped**.
  [Окружение](examples/backend_stage7_clean_environment.json),
  [JUnit](examples/backend_stage7_clean_pytest.xml),
  [сценарий](examples/backend_stage7_clean_flow.json).

Критерии плана дополнительно закреплены автоматическими проверками:

| Критерий | Проверки |
|---|---|
| Решение одинаково учитывают agent/search/evidence | [test_conflict_resolution](../tests/test_conflict_resolution.py) |
| Чужая версия, пустая причина, 409, конкурентный повтор | [test_conflict_resolution](../tests/test_conflict_resolution.py), [test_api_contract](../tests/test_api_contract.py) |
| Несколько конфликтов, новое противоречие, TTL, будущие факты, симуляция | [test_conflict_resolution](../tests/test_conflict_resolution.py) |
| Требования относятся к одному номеру | [test_ranking](../tests/test_ranking.py), [test_registry_extension](../tests/test_registry_extension.py) |
| Повторное открытие вопроса, неполный ответ, история | [test_question_lifecycle](../tests/test_question_lifecycle.py) |
| Откат всей операции при ошибке | [test_question_lifecycle](../tests/test_question_lifecycle.py), [test_conflict_resolution](../tests/test_conflict_resolution.py) |
| Сохранение старой БД, повторная миграция, откат DDL | [test_migrations](../tests/test_migrations.py) |
| Новая характеристика от реестра до поиска и UI | [test_registry_extension](../tests/test_registry_extension.py) |
| ML-контракт, цитаты, отрицания/условия, ошибки провайдера | [test_reply_parser](../tests/test_reply_parser.py), [test_reply_http](../tests/test_reply_http.py) |
| Параметры поиска сохраняются после действия владельца | [test_conflict_frontend](../tests/test_conflict_frontend.py) |

## Что ещё нужно проверить

1. **Реальная LLM, этап 4 и часть этапа 7.** Повторный
   [preflight](examples/backend_stage7_ml_preflight.json) показал:
   `missing_GROQ_API_KEY`, локальная Ollama — `provider_unavailable`.
   Генерация не запускалась, метрик качества нет. После подключения модели:

   ```bash
   python -m scripts.benchmark_models --profiles local-gemma12b groq-120b --output runtime/model_preflight.json
   python -m scripts.benchmark_models --profiles local-gemma12b --run --split held_out --output runtime/model_results.json
   ```

   Для облака во второй команде выберите `groq-120b`. Отдельно включите
   `REPLY_PARSER_MODE=ollama` или `groq` и пройдите новые ответы отельера по
   [инструкции ML](REPLY_PARSER_INTEGRATION.md). Проверить новые формулировки,
   отрицания, числовые ограничения, неоднозначность и условия; сохранять исходный
   текст и фактический ответ. Синтетический набор 44 случая требует проверки человеком.
2. **Визуальный браузерный QA.** В текущей сессии браузеров/приложений нет,
   native pipe не запускается. Нужен просмотр карты, узкого экрана и длинных названий.
3. **Внешний NoiseModelling** — запустить пропущенную проверку в настроенной
   среде по [ENVIRONMENT](ENVIRONMENT.md). Оценочные геоданные и учебная акустика
   сохраняют прежние ограничения; полевой проверки они не заменяют.

## Комплект исходников

```bash
python -m scripts.package_demo
```

Получаются `artifacts/ostrovok-adler-mvp.zip` и соседний `.zip.sha256`.
В архив входят код, миграции, тесты, документация, JSON-примеры и демо-данные.
Рабочая БД, `.env`, `.venv`, `.git` и `runtime/` не включаются.
Наличие ZIP не означает commit/push или публикацию.
Исходный ZIP для чистой установки собран до добавления итоговых отчётов;
код, тесты, миграции и данные финального архива сверены с проверенной копией.
Итоговая проверка содержимого и checksum записана рядом с архивом в
`artifacts/ostrovok-adler-mvp.verification.json`.

После приёмки удалены старая вложенная `Островок/`, временная распакованная
копия с отдельной `.venv` и кэши Python/pytest. Сохранены основная среда,
рабочая БД, резервные копии и отчёты; пути временной чистой установки в
исторических JSON относятся к завершённой проверке, сама копия уже удалена.
Повторная проверка после очистки: [отчёт](examples/backend_cleanup_validation.json).
