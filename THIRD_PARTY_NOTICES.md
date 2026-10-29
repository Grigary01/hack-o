# Происхождение кода и данных

## agent_tool_map

Автор: Maxim (MaximShalankin), Copyright (c) 2025 Maxim.
Источник: <https://github.com/MaximShalankin/agent_tool_map>.
Исследован commit `45ad71a637f1c7bbf561934326cbd8854f27f118`.
Оригинальная MIT-лицензия сохранена без изменений в корневом `LICENSE`.
Неизменённые исходные файлы с лицензией: `legacy/agent_tool_map_45ad71a.zip`.
Отдельный локальный git clone не требуется: исходники и лицензия сохранены в указанном архиве.

Адаптированы идеи и фрагменты:
- `OSMSearchEngine._execute_poi_search/_get_cache_key` → `app/geo/osm_provider.py`: union выборок, словарь тегов, SHA256. JSON вместо pickle, geometry и provenance, явные ошибки.
- `POISearchDemo.score_pois_by_proximity` → `app/ml/ranking.py`: inverse-distance match; исправлена обработка нулевого расстояния, добавлены hard filters и coverage.
- `MapEngine` → `frontend/map_view.py`: FeatureGroup/Marker/PolyLine/LayerControl; сокращённый интерфейс, HTML escaping и отдельная локальная SVG-схема.

Новые модули SQLAlchemy, Pydantic, FastAPI, маршрутизация, реестр, диалог и проверки созданы для этого MVP.
Старые движки не импортируются при запуске.

## OpenStreetMap

`data/demo/osm_snapshot.json`, `walk.graphml`, `osm_cache/`, производные hotel/features и маршруты:
**© OpenStreetMap contributors**, [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
Данные/производная база OSM распространяются на условиях ODbL; MIT относится к коду, не заменяет лицензию данных.
[Attribution и лицензия OSM](https://www.openstreetmap.org/copyright).
Источники, времена, запросы и bbox доступны внутри snapshots. Данные Островка не использовались.

Кэш OSMnx сохранён для аудита полученного ответа; не загружаются массово тайлы.
Карта в интерфейсе — схема без подложки: внешние тайлы не загружаются.
Демо-запросы и синтетические unit-test объекты отделены от реальных OSM-данных.
Симулированные room facts записываются только в локальную runtime DB, не в реальный геодатасет.

## Copernicus DEM

`data/environment/dem_copernicus_glo30.npz` — окно Copernicus DEM GLO-30 (43.30–43.65° с.ш.,
39.65–40.10° в.д.), прочитанное из публичных COG на AWS (`copernicus-dem-30m`), высоты в дециметрах.
© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS
by the European Union and ESA; all rights reserved. Использование по лицензии Copernicus DEM
(бесплатно, с указанием источника). URL тайлов, SHA256 и дата — в `dem_copernicus_glo30.json`.

## Зависимости

Зависимости устанавливаются из Python package index; версии, использованные при проверке, закреплены
в `requirements.lock`. Их собственные лицензии остаются в пакетах. Оригинальные пользовательские
материалы лежат в `docs/inputs/` отдельно от документации реализации.

## NoiseModelling, OpenAQ и модели

Внешний NoiseModelling 5.0.1, Université Gustave Eiffel и соавторы, GPL-3.0:
https://github.com/Universite-Gustave-Eiffel/NoiseModelling. Скачивается отдельным
installer в runtime/tools, вызывается отдельным CLI. Его лицензия сохранена в
официальном дистрибутиве; бинарники и исходники движка не включены в наш ZIP/Git.
Наш адаптер готовит входы и читает результаты; акустические алгоритмы не наши.
Java Temurin 17 использована локально; её лицензия сохранена в дистрибутиве,
бинарники не включены в поставку.

OpenAQ v3: https://docs.openaq.org/. Нужен личный ключ; условия upstream-провайдеров
измерений сохраняют силу. Доступные provider/licenses сохраняются в отчётах.
Живых измерений OpenAQ пока нет. Mock-ответы тестов синтетические.
Данные data/environment/osm_buildings.json и производная геометрия:
© OpenStreetMap contributors, ODbL 1.0. Сценарный трафик условный, не измеренный.
Веса GPT-OSS/Qwen/Gemma не скачиваются и не распространяются с проектом;
облачный Groq имеет собственные условия и квоты аккаунта.
