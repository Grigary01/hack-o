# Реестр характеристик

Источник истины — `app/features/registry.yaml`; загрузка и валидация — `registry.py`.
Значения типов/единиц/scope проверяются как для запросов, так и для наблюдений.

| Ключ | Тип / scope | Provider | TTL | Вес по умолчанию |
|---|---|---|---|---|
| walking_distance_to_beach_m | number m / hotel | pedestrian_distance | 90 дней | .8 |
| quietness_proxy | low/medium/high / hotel | quietness | 90 дней | .9 |
| nightlife_distance_m | number m / hotel | nightlife_distance | 60 дней | .7 |
| sea_view | boolean / room | hotelier | 90 дней | .6 |
| soundproofing | boolean / room | hotelier | 180 дней | .7 |
| sunset_view | boolean / room | hotelier | 90 дней | .6 |
| blackout_curtains | boolean / room | hotelier | 180 дней | .5 |

Quietness: дороги motorway/trunk=1, primary=.9, secondary=.7, tertiary=.5,
residential=.3, service=.15, unclassified=.4; decay scale=120 м.
Rail=1, scale=180 м; nightlife=.6, scale=100 м. Максимум из `w*exp(-d/scale)` — risk.
High quietness при risk<.25, medium при <.6, иначе low. Это экспертная некалиброванная эвристика.

`nightlife_distance_m` — по прямой в локальной проекции, до ближайшего **известного** заведения;
не пеший путь. Отсутствие заведений в данных даёт unknown, не «баров нет».
Sea/sunset/soundproofing/blackout — только утверждения о конкретных номерах; DEM не реализован.

## Добавление без изменения Python-кода

`blackout_curtains` уже включён в основной реестр. Его полный путь описан в
[REGISTRY_EXTENSION](REGISTRY_EXTENSION.md). Следующий boolean room-признак
можно добавить в YAML, например:

```yaml
reading_lamp:
  label: Лампа для чтения
  description: Утверждение отельера о конкретном номере
  type: boolean
  scope: room
  unit: null
  provider: hotelier
  ttl_days: 180
  default_weight: 0.5
  aliases: [лампа для чтения, лампы для чтения]
  question: В каких конкретных номерах есть или нет лампы для чтения?
```

Перезапустите backend и выполните `python -m scripts.seed_demo`, чтобы обновить
снимок определений в БД; повторный seed сохраняет ответы. Характеристика появится
в `/api/features` и кабинете. Ответ «В номере 501 есть лампа для чтения»
разбирается существующим provider, сохраняется после confirmation. Structured search принимает новый ключ;
Ollama/Groq получают обновлённые описания, aliases и JSON-схемы. Для offline fixture-парсера добавьте отдельный явный пример запроса:
он сознательно не интерпретирует произвольный текст. Новый provider по имени сам не запускается — нужен whitelist.

Rules-парсер ищет aliases по границам слов; «неплотные шторы» не совпадают с
«плотные шторы». Неизвестные/условные фразы требуют уточнения; цитаты и claims
проверяются перед сохранением и подтверждением. Синонимы и словоформы нужно указать явно.

Расширение этим способом проверено `tests/test_feature_agent.py` (временный `reading_lamp`)
и `tests/test_registry_extension.py` (полный путь `blackout_curtains`). Для нового способа вычисления
(например, DEM/viewshed) необходим реальный calculator, его ToolSpec и тесты; текст YAML не создаёт геоданные.
