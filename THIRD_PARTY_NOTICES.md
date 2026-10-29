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
Подложку карты в интерфейсе браузер загружает с OpenFreeMap (см. раздел «Интерфейс web/»).
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

## Интерфейс web/: карта и фотографии

- **Карта** — [MapLibre GL JS](https://github.com/maplibre/maplibre-gl-js) (BSD-3-Clause) с векторной
  подложкой [OpenFreeMap](https://openfreemap.org/) (стиль Liberty, без ключа).
  Данные подложки © [OpenMapTiles](https://www.openmaptiles.org/), © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright) (ODbL).
  Атрибуция выводится на самой карте. Подложка загружается браузером из сети; без сети показывается
  SVG-схема по координатам.
- **Фотографии** — стоковые снимки [Unsplash](https://unsplash.com/) по [Unsplash License](https://unsplash.com/license)
  (свободное использование, в т. ч. коммерческое, без обязательной атрибуции). Это **не фото конкретных
  отелей**: в интерфейсе они подписаны «Фото для примера», в alt — «Иллюстративное фото». Своих фото у
  отелей из OSM нет; при наличии сайта отеля в OSM на странице отеля есть ссылка на него.

| Файл | Источник |
|---|---|
| `web/public/photos/hotel-1.webp` | https://images.unsplash.com/photo-1455587734955-081b22074882 |
| `web/public/photos/hotel-2.webp` | https://images.unsplash.com/photo-1551882547-ff40c63fe5fa |
| `web/public/photos/hotel-3.webp` | https://images.unsplash.com/photo-1564501049412-61c2a3083791 |
| `web/public/photos/hotel-4.webp` | https://images.unsplash.com/photo-1568084680786-a84f91d1153c |
| `web/public/photos/hotel-5.webp` | https://images.unsplash.com/photo-1615460549969-36fa19521a4f |
| `web/public/photos/hotel-6.webp` | https://images.unsplash.com/photo-1542314831-068cd1dbfeeb |
| `web/public/photos/hotel-7.webp` | https://images.unsplash.com/photo-1561501900-3701fa6a0864 |
| `web/public/photos/hotel-8.webp` | https://images.unsplash.com/photo-1566073771259-6a8506099945 |
| `web/public/photos/room-1.webp` | https://images.unsplash.com/photo-1590490360182-c33d57733427 |
| `web/public/photos/room-2.webp` | https://images.unsplash.com/photo-1618773928121-c32242e63f39 |
| `web/public/photos/room-3.webp` | https://images.unsplash.com/photo-1631049307264-da0ec9d70304 |
| `web/public/photos/room-4.webp` | https://images.unsplash.com/photo-1611892440504-42a792e24d32 |
| `web/public/photos/room-5.webp` | https://images.unsplash.com/photo-1582719478250-c89cae4dc85b |
