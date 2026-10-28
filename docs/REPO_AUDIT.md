# Аудит исходного проекта

Прочитан реальный код [agent_tool_map](https://github.com/MaximShalankin/agent_tool_map),
commit `45ad71a637f1c7bbf561934326cbd8854f27f118` (ветка main).
Неизменённые исходники сохранены в `legacy/agent_tool_map_45ad71a.zip`.
Это справочный код, не entrypoint MVP; отдельного `upstream/` в текущей папке нет.
Аудит выполнен до реализации. Ни BIO, ни embeddings, ни MCP, ни маршрутизации по графу в нём нет.

| Исходный файл и функция | Реальное поведение | Решение / новый модуль |
|---|---|---|
| `demo.py:POISearchDemo.analyze_query` | Выделяет текст между первой и последней фигурной скобкой; dataclass без проверки типов | Заменить на JSON Schema + Pydantic в `app/ml/query_parser.py` |
| `demo.py:score_pois_by_proximity` | `1/(1+d/1000)` и отсечение 2 км; ноль метров теряется из-за `if distance` | Сохранить понятную inverse-distance функцию, исправить ноль, разделить hard/soft в `app/ml/ranking.py` |
| `demo.py:run_search` | При отсутствии матрицы/вторичных POI присваивает всем 1.0 | Убрать фиктивный match; unknown и coverage |
| `engines/agent_engine/engine.py:OllamaClient.generate` | HTTP запрос, параметры temperature/max_tokens на верхнем уровне, max_retries не используется | Сохранить HTTP-адаптер как идею; `options.temperature/num_predict`, schema, ограниченные повторы |
| `MapAgent.process_query`, `_analyze_query`, `_search_pois` | Фиксированная цепочка; русский `в` передаётся английскому keyword parser; search_radius теряется | `app/agent/feature_agent.py`: выбор инструмента по реестру, видимый trace и бюджет |
| `MapAgent._create_route_visualization` и другие | Heatmap/routes/area возвращают обычные маркеры | Не считать реализованной маршрутизацией; показывать настоящую полилинию |
| `MapAgent._update_average_time`, `test_connection` | Среднее не обновляется из process_query; health движков захардкожен True | Новая health проверяет DB/seed, не делает вид, что проверила внешние API |
| `engines/map_search_engine/engine.py:_execute_poi_search`, `_map_categories_to_tags` | Полезная union-выгрузка node/way/relation, словарь OSM-тегов | Адаптировать в `app/geo/osm_provider.py`; сохранить тип и ID, geometry и сырой JSON |
| `_get_cache_key`, `_execute_query_with_retry` | SHA256, TTL и backoff полезны; pickle; ошибки маскируются пустой выборкой; некоторые последние retry возвращают None | JSON cache, явные ошибки/таймауты/два повтора; отдельный ingestion |
| `calculate_distance_matrix`, `_calculate_geographic_distance_matrix` | geopy.geodesic для всех profiles. Foot лишь делит метры на 1.4 | Заменить `app/geo/routing.py`: OSMnx walking graph + NetworkX Dijkstra. Геодезия только для привязки и диагностики |
| `CityBounds.calculate_area` | Долгота умножена на abs(latitude), а не cos(latitude) | Не переносить; небольшой явный bbox в конфигурации |
| `search_pois`, `parse_search_query` | При потере географии молча ищет в Москве; parser английский | Только поддерживаемый Адлер; неподдерживаемый регион требует уточнения |
| `engines/map_viz_engine/engine.py:MapEngine` | Реальные Folium FeatureGroup, маркеры, PolyLine, LayerControl | Переиспользовать сокращённый адаптер `frontend/map_view.py`; экранировать текст OSM в popup |
| `config.py` | gemma3:12b, но agent/README default gpt-oss:20b | Один env-конфиг `app/core/config.py` |
| `requirements.txt` | Нижние границы без lock; folium импортируется, но не объявлен напрямую | pyproject + проверенный lock; OSMnx только для offline подготовки |
| `readme.md` | Несуществующий `demo_vacation_search.py` | Новый README с выполненными командами |
| `tests/test_engine_comprehensive.py` | Живые API, условные проверки `if result`; тест площади проверяет лишь >0 | Изолированные тесты с невозможным проходом, закрытым доступом и no path |
| `tests/test_agent_engine_comprehensive.py` | Частично mock, частично сеть/Ollama; часто допускает None | Контрактные unit/integration tests без внешней сети |
| `tests/test_map_engine.py` | Скрипт run_tests, не pytest test_* | Новый UI smoke + проверка экранирования |

Сохраняем MIT LICENSE и ссылку на автора. Архив исходных файлов сохранён в `legacy/agent_tool_map_45ad71a.zip`.
Столбец «Решение» фиксирует вывод первоначального аудита; перечисленные новые модули реализованы,
их фактическая готовность и ограничения указаны в [TASKS](TASKS.md).
Новые модули не импортируют старый монолит: так ошибки прежней семантики не попадут в MVP.
