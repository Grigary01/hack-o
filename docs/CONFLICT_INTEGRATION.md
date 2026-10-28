# Этап 2: решение конфликтов и подключение frontend/ML

Решение хранится отдельно от конфликта и наблюдений. Поиск, агент и evidence
используют один `resolve_feature()`. Исходные ответы, даты, confidence, TTL и
источник сохраняются. Решение не делает симуляцию реальным фактом.

## HTTP-контракт для frontend

Все новые операции доступны только при `DEMO_MODE=true`, без реальной
авторизации отельера. `operator_id=demo_operator` задаёт сервер; клиент его
не передаёт. Перед первым запуском старой базы выполните
[миграцию](MIGRATIONS.md).

```text
GET /api/hotelier/conflicts?hotel_id=...&status=open
GET /api/hotelier/conflicts?status=resolved
POST /api/hotelier/conflicts/{conflict_id}/resolve
```

GET возвращает массив `ConflictDetail`. В нём сохранены `id`, `hotel_id`,
`subject_id`, `feature_key`, `left_id`, `right_id`, `created_at`, `policy`;
добавлены `status`, `resolution`, `left_observation`, `right_observation`.
Обе версии доступны сразу для отображения, включая источники и цитаты.
Отсутствие фильтра `hotel_id` возвращает конфликты всех отелей демо-базы.

Тело POST:

```json
{
  "selected_observation_id": "ID одной из двух версий конфликта",
  "reason": "Почему выбран этот ответ"
}
```

Ответ POST: `conflict_id`, `status=resolved`, `resolution`, `idempotent`,
`current`. Решение содержит `conflict_id`, `selected_observation_id`, `reason`,
`resolved_at`, `operator_id`. `current` содержит `subject_id`, `feature_key`,
`value`, `status`, историю `observations` и `resolved_conflict_ids`.
Это текущее состояние с включённой симуляцией, как `current_demo` в evidence.

`resolved` у записи конфликта означает наличие сохранённого решения. Это не
гарантия пригодности факта сейчас: для этого смотрите `current.status/value`
или evidence. При другом нерешённом конфликте current останется `conflicted`;
при истечении TTL выбранный факт перестанет удовлетворять условиям.

| Код | Значение |
|---|---|
| 200 | Сохранено либо одинаковое решение повторено (`idempotent=true`) |
| 403 | Симулятор выключен |
| 404 | Нет конфликта, наблюдения или указанного отеля |
| 409 | Этот конфликт уже решён с другим выбором или другой причиной |
| 422 | Пустая/слишком длинная причина, чужое наблюдение, неизвестные поля/фильтр |

Одно решение рассматривает только указанную пару свидетельств. Новое
противоречие создаёт новый конфликт. Все активные противоречащие пары должны
иметь согласованные решения. Отвергнутая версия не становится текущей снова,
если выбранная устарела. Состояния `estimated`/`verified` не повышаются решением.

## Заглушка frontend без сервера

Статический сценарий выгружен настоящим API в
[conflict_integration_fixture.json](examples/conflict_integration_fixture.json).
Он явно помечен `fixture_only`; ответы о номере симулированы. JSON содержит
открытый и решённый конфликт, запрос/ответ решения, отель и распознанный запрос.

```python
from frontend.conflict_client import ConflictClient
from frontend.conflict_stub import StubConflictAPI

stub = StubConflictAPI()
client = ConflictClient(api=stub)
conflict = client.list_conflicts(status='open')[0]
request = stub.fixture['resolution_request']
response = client.resolve_conflict(conflict['id'], **request)
assert response['current']['value'] is True
assert client.list_conflicts(status='open') == []
```

Для подключения к настоящему backend меняется только создание клиента:

```python
from frontend.api_client import APIClient
client = ConflictClient(api=APIClient(base_url='http://127.0.0.1:8000'))
```

Заглушка поддерживает один заданный сценарий и повтор того же решения.
Произвольный выбор/причину проверяйте с backend. Заглушка не включается
автоматически, не пишет в SQLite и не участвует в настоящем поиске.
Кнопка решения подключена в этапе 5: [экран и API-контракт](API_FRONTEND_INTEGRATION.md).

Для обновления JSON по фактическому API:

```bash
python -m scripts.export_conflict_contract
```

Экспорт создаёт отдельную in-memory SQLite и использует существующий
`FixtureQueryParser`. Он не запускает настоящую LLM и не изменяет рабочие ответы.

## Контракт ML

`ParsedHotelQuery` и `ReplyExtraction` не менялись. Существующий
`FixtureQueryParser` остаётся явной заглушкой понимания текста. Замена обработчика
ответа отельера будет отдельным этапом 4; в этом этапе модели не подключались.

Ранжирование принимает необязательный keyword-аргумент `conflicts`:

```python
from app.schemas.conflicts import ConflictDetail
from app.ml.ranking import rank_hotels

conflicts = [ConflictDetail.model_validate(item) for item in api_conflicts]
result = rank_hotels(
    parsed_query,
    [(hotel, observations)],
    include_simulated=True,
    ranking_method='balanced_v2',
    balance=0.25,
    conflicts=conflicts,
)
```

Здесь `parsed_query`, `hotel`, `observations` — существующие Pydantic-контракты,
`api_conflicts` — результат GET. Для вызова внутри backend используется
`repo.conflict_records()`; ML не открывает базу. Старые вызовы без `conflicts`
работают и продолжают блокировать противоречащие значения.

Формат результата поиска, методы ранжирования, `balance`, `include_simulated`
и три группы выдачи сохранены. В evidence добавлено поле `resolved_conflict_ids`.
История наблюдений остаётся полной, включая отвергнутые версии.

## Проверено

- Общий набор: 89 passed, 1 skipped; пропущен внешний NoiseModelling.
- Настоящий `ConflictClient` прошёл HTTP → решение → поиск → перезапуск SQLite.
- Новый противоречащий ответ снова блокирует только спорный факт.
- Тесты проверяют контракт заглушки и передачу того же JSON в чистое ранжирование.
- Проверены несколько конфликтов, несовместимые решения, TTL, симуляция,
  неподходящее свидетельство, повторные/конкурентные запросы и откат транзакции.

Отчёты: [Pytest](examples/backend_stage2_pytest.xml),
[HTTP/SQLite](examples/backend_stage2_flow.json),
[проверка всех 75 геонаблюдений](examples/backend_stage2_data_validation.json).
Состав исходной поставки проверен: миграции и fixture включены;
рабочие SQLite, резервные копии и секреты исключены.
Браузерная визуальная проверка не выполнялась: браузер недоступен в сессии.
Реальное качество ML не оценивалось.

В этапе 2 жизненный цикл вопросов ещё не менялся. Теперь этап 3 выполнен:
повторное открытие при конфликте/устаревании и закрытие после устранения причины.
Новые поля очереди, фильтры и заглушки: [QUESTION_INTEGRATION](QUESTION_INTEGRATION.md).
