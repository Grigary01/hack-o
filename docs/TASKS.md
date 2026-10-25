# Готовность и распределение работы

Имена участников не предоставлены. Закрепление: **У1 ML**, **У2 Geo/Data**, **У3 Backend/Agent/Storage**,
**У4 Frontend**. QA/интеграцию совместно выполняют У3 и У4; метрики проверяют владельцы модулей.
Пофайловое закрепление — PROJECT_STRUCTURE.md. Статусы относятся к коду в этой папке, не к исходному blueprint.

## Пять обязательных требований

| Требование | Статус | Реализация и доказательство | Граница |
|---|---|---|---|
| 1. Агент собирает и вычисляет | DONE (MVP) | `app/agent/*`, `app/geo/*`; 25 отелей, 23 маршрута, trace выбора tool; test_feature_agent/test_geo_routes | Constrained rules planner; входы оценочные, нет автономного web research |
| 2. Диалог с отельером | DONE (MVP) | `app/hotelier/dialogue.py`, `app/api/hotelier.py`, UI; range/negation, confirmation, persist | Симуляция; bounded grammar, сложный текст требует уточнения |
| 3. Хранение и достоверность | DONE (MVP) | `app/storage/*`, `app/features/service.py`; source/date/confidence, TTL, обе версии конфликта | Конфликт блокирует факт и возвращает к вопросу; ручной resolver ещё TODO |
| 4. Расширяемость | DONE (MVP) | YAML boolean room feature + existing hotelier provider; тест blackout_curtains | Новая геоматематика требует calculator; fixture-запрос добавляется отдельно |
| 5. Поиск по запросу | DONE для demo; IN_PROGRESS для качества свободного NLP | 12 offline формулировок, typed filters/ranking; Ollama schema adapter | Реальная модель не запускалась; универсальное качество не подтверждено |

## Уже сделано дополнительно

- DONE — **У1**: hard/soft separation, веса, same-room matching, coverage; [ranking](../app/ml/ranking.py).
- DONE — **У1**: 44 авторских gold cases, 12 demo/32 held-out и честный evaluator; [evaluation](../scripts/evaluate_parser.py).
- DONE — **У2**: raw OSM, GraphML, checksum, все 75 значений воспроизводятся; [validator](../scripts/validate_data.py).
- DONE — **У3**: идемпотентный seed/confirmation и история; [repository](../app/storage/repository.py).
- DONE — **У4**: локальная карта без сети, опциональная Folium-карта, сравнение до 3 отелей, слайдеры, evidence и кабинет; [frontend](../frontend/app.py).
- DONE — **У3/У4**: 40 автоматических проверок, API и Streamlit AppTest без внешней сети; [VALIDATION](VALIDATION.md).
- DONE — **У1**: подробные комментарии к ML/контрактам/evaluator и пошаговый [ML_GUIDE](ML_GUIDE.md).
- DONE — **У3**: ZIP с исходниками и данными, SHA256, smoke из чистой распаковки; [package_demo](../scripts/package_demo.py).

## Следующие задачи с критериями приёмки

- **P0 / У1 / TODO** — Запустить локальную Ollama с выбранной моделью и evaluator на 32 held-out случаях.
  Файлы `app/ml/prompts.py`, `scripts/evaluate_parser.py`. Готово, когда сохранены фактические метрики,
  разобраны ошибки чисел/отрицаний/городов, улучшения не проверяются только на few-shot примерах.
- **P0 / У2 / TODO** — Ручная проверка входов/ограждений и проходов на пляж для 5–10 маршрутов.
  `app/geo/routing.py`, новый `data/evaluation/routes_gold.json`. Готово, когда есть отдельные проверяемые
  источники/дата и сравнение расчётов с проверенной проходимой трассой. Не менять low confidence без оснований.
- **P0 / У4 / TODO** — Визуальная проверка в браузере, в том числе узкий экран, длинные названия и карта.
  `frontend/app.py`. Готово, когда просмотрены реальные экраны; AppTest не заменяет визуальный QA.
- **P1 / У3 / TODO** — Разрешение конфликта оператором с причиной, выбранной версией и историей решений.
  `app/features/service.py`, `app/storage/models.py`, `app/api/hotelier.py`. Готово: конфликт не удаляется,
  выбранное значение возвращается в поиск только после явного решения, есть тесты.
- **P1 / У1+У3 / TODO** — Ollama structured extractor свободных ответов отельера с условиями/сезонностью;
  `app/hotelier/dialogue.py`, `app/schemas/hotelier.py`. Готово: gold replies, сохранённые цитаты,
  scope/условия не теряются, confirmation остаётся обязательным.
- **P1 / У2 / TODO** — Добавить авиационный фактор/другой независимый источник шума и калибровку;
  `app/geo/quietness.py`. Готово: источники, метод, метрика против размеченной проверки; не выдавать дБ без модели.
- **P1 / У2+У3 / TODO** — Плановое обновление snapshot с версионированием и обработкой удалённых отелей.
  `scripts/collect_adler_osm.py`, `app/storage/repository.py`. Сейчас TTL учитывается, но автоматической загрузки нет.
- **P1 / У3 / TODO** — Авторизация реального отельера, ownership, миграции SQLite и проверки конкурентных записей.
  `app/api/hotelier.py`, `app/storage/*`. Нельзя публиковать текущий симулятор как реальный кабинет.
- **P2 / У2 / TODO** — DEM/buildings/facade/floor viewshed, только при достаточных источниках.
  Будущий `app/geo/viewshed.py` пока намеренно не создан.
- **P2 / У1 / TODO** — Semantic retrieval описаний после детерминированных фильтров; embeddings сейчас не нужны.
- **P2 / У4 / TODO** — React-клиент только при доказанной потребности; API позволяет заменить Streamlit.

## Ограничения среды

Браузерный UI-инструмент недоступен (`CUA_REPL_ENABLED_SURFACES is required`); визуальный QA не заявляется.
Ollama отсутствует в PATH; модель не скачивалась. Это ограничения проверки, не маскируются DONE.
Для Git используется отдельная рабочая копия `runtime/publish/hack-o/`, чтобы не затронуть репозиторий домашнего каталога.
Ветка разработки — `development/adler-mvp` в `Grigary01/hack-o`; оригинальный проект сохранён в `upstream/` и `legacy/`.
