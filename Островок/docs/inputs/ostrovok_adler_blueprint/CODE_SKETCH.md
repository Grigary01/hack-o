# Набросок интерфейсов Python — как должен выглядеть код

> Это **контрактный эскиз**, не готовый к запуску репозиторий. Он помогает ML/Geo/Backend/Frontend заранее согласовать имена и форматы. Coding-агент должен реализовать код полностью и проверить его. Не вставляйте всё в `demo.py`.

## 1. ML: `app/schemas/query.py`

```python
from typing import Literal
from pydantic import BaseModel, Field

class HardConstraint(BaseModel):
    feature_key: str  # проверяется по features/registry.yaml
    operator: Literal["<", "<=", "=", ">=", ">", "!="]
    value: float | bool | str
    unit: str | None = None
    scope: Literal["hotel", "room"] = "hotel"

class SoftPreference(BaseModel):
    feature_key: str
    desired: str | float | bool
    importance: float = Field(default=0.5, ge=0, le=1)
    weight_source: Literal["default", "explicit", "relative_inferred"] = "default"
    scope: Literal["hotel", "room"] = "hotel"

class ParsedHotelQuery(BaseModel):
    region: str = "Adler"
    hard_constraints: list[HardConstraint] = Field(default_factory=list)
    soft_preferences: list[SoftPreference] = Field(default_factory=list)
    unknown_or_ambiguous: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    original_text: str = ""
```

В реальном коде: строгие правила диапазонов/единиц, отдельные модели для числовых и булевых условий, обработка relative importance и валидаторы `feature_key`. Если модель не распознаёт условие, сохранять его в `unknown_or_ambiguous`, а не удалять без предупреждения.

## 2. ML: `app/ml/query_parser.py`

```python
class QueryParser:
    def parse(self, text: str) -> ParsedHotelQuery:
        """Разбирает свободный русский запрос.

        1. Отправляет structured request в Ollama с JSON Schema.
        2. Валидирует ответ Pydantic.
        3. Нормализует км -> м, отрицания, алиасы feature registry.
        4. Если нельзя распарсить -- возвращает явную ошибку или clarification.
        """
        ...
```

Сделайте две реализации: `OllamaQueryParser` и `FixtureQueryParser`, который возвращает заранее проверенные ответы для демонстрационных запросов. Провайдер выбирается конфигом/DI, не условным `if` в каждом endpoint.

## 3. Geo: `app/geo/routing.py`

```python
class PedestrianRouter:
    def __init__(self, graph):
        self.graph = graph  # OSMnx/NetworkX graph, загружается заранее

    def distance_to_beach(self, hotel, beach_access):
        """Возвращает Observation с длиной пути, качеством и source.

        1. Берём реальные точки входа отеля и доступного входа на пляж.
        2. Привязываем координаты к пешеходному графу.
        3. OSMnx shortest_path(..., weight='length').
        4. Суммируем длины рёбер + учитываем/оцениваем отрезки привязки.
        5. Если нет пути -- status='unknown', НЕ geodesic под видом foot.
        """
        ...
```

```python
# Иллюстрация центрального расчёта, не полный код:
import osmnx as ox

start = ox.distance.nearest_nodes(graph, X=hotel_lon, Y=hotel_lat)
end = ox.distance.nearest_nodes(graph, X=access_lon, Y=access_lat)
route = ox.routing.shortest_path(graph, start, end, weight="length")
if route is None:
    return None  # вызывающий код превращает в unknown observation
route_edges = ox.routing.route_to_gdf(graph, route)
route_distance_m = float(route_edges["length"].sum())
```

Остерегайтесь перепутать координаты: OSMnx в `nearest_nodes` принимает `(X=longitude, Y=latitude)`, а `graph_from_point` обычно принимает `(latitude, longitude)`.

## 4. Единый формат фактов: `app/schemas/hotel.py`

```python
from datetime import datetime
from pydantic import BaseModel, Field

class FeatureObservationDTO(BaseModel):
    subject_type: str            # hotel | room
    subject_id: str
    feature_key: str
    value: str | float | bool | None
    unit: str | None = None
    status: str                  # verified | estimated | unknown | ...
    source_type: str
    source_ref: str | None = None
    method: str
    collected_at: datetime
    expires_at: datetime | None = None
    confidence_level: str          # high | medium | low | unknown
    confidence: float | None = None
    confidence_method: str         # причина присвоенного уровня/оценки
    quality_flags: list[str] = Field(default_factory=list)
```

В реальном файле нужны строгие enums, evidence/observed_at и аккуратная сериализация дат. `confidence` нельзя выдавать как точную вероятность без калибровки.

## 5. Agent: `app/agent/feature_agent.py`

```python
class FeatureAgent:
    def get_or_collect(self, hotel_id: str, feature_key: str):
        """Найти действующее наблюдение либо выбрать разрешённый инструмент.

        - Если свежий verified/estimated факт уже есть: вернуть его.
        - По feature registry выбрать допустимый инструмент из whitelist.
        - Выполнить tool, зафиксировать source / evidence / method.
        - Если данные невычислимы / неполны: status unknown и вопрос отельеру.
        - Если новые данные противоречат старым: создать Conflict.
        """
        ...
```

Отдельно сделайте `FeatureRegistry`, `ToolSpec`, `ToolResult`, `PlannerDecision` и строгую валидацию аргументов. Чтобы удовлетворить agent-часть ТЗ, агент должен **выбирать** подходящий источник/инструмент для запрашиваемой характеристики и это решение должно быть видно в trace. Если выбор детерминированный по реестру, так честно и опишите; LLM tool calling добавьте при необходимости сложных маршрутов.

## 6. Ranking: `app/ml/ranking.py`

```python
class HotelRanker:
    def rank(self, parsed: ParsedHotelQuery, hotel_facts: list):
        """Рейтинг без выдуманных фактов.

        1. Проверить hard constraints с учётом единиц и scope.
        2. Подтверждённо нарушил hard condition -> исключить.
        3. Unknown hard value -> отложить в needs_verification.
        4. Для известных soft prefs считать интерпретируемый match 0..1.
        5. Добавить coverage/uncertainty и объяснение с источниками.
        """
        ...
```

Рекомендуемая понятная формула среди *известных* мягких свойств:

```text
soft_score = sum(weight_i * match_i for known i) / sum(weight_i for known i)
coverage = sum(weight_i for known i) / sum(weight_i for all requested i)
```

Показывайте **обе** метрики; когда `coverage = 0`, не присваивайте высокий match. Вес `0` исключается из знаменателя; отсутствие данных не превращается в позитивную оценку. Строгие условия не усредняйте с мягкими.

## 7. Backend: `app/api/search.py`

```python
from fastapi import APIRouter
router = APIRouter(prefix="/api", tags=["search"])

@router.post("/parse-query")
def parse_query(request: ParseQueryRequest):
    # DI parser instance; validate and return ParsedHotelQuery
    ...

@router.post("/search")
def search(request: SearchRequest):
    # 1) Parse request or accept typed query
    # 2) Query DB / feature agent
    # 3) Rank
    # 4) Return candidates with match/violated/unknown and evidence
    ...
```

Создайте явные модели `ParseQueryRequest`, `SearchRequest`, `SearchResponse`, `HotelSearchResult` в `app/schemas/`; не `dict[str, Any]` повсюду. Не обращайтесь к OSM прямо внутри FastAPI endpoint при demo mode.

## 8. Frontend: `frontend/api_client.py`, `frontend/app.py`

```python
# frontend/api_client.py
import requests

def search_hotels(api_url: str, text: str, weights: dict[str, float]):
    response = requests.post(
        f"{api_url}/api/search",
        json={"text": text, "weights": weights},
        timeout=20
    )
    response.raise_for_status()
    return response.json()
```

```python
# frontend/app.py — упрощённый дизайн, реализацию доделать
import streamlit as st

query = st.text_input("Какой отель ищете?")
# Показать распознанные preferences, настроить weights через sliders
# По кнопке вызвать search_hotels() и отрисовать карточки/evidence
# Второй экран: hotelier demo -> answer -> confirm -> refresh search
```

## 9. Тесты должны соответствовать контракту

```python
def test_hard_constraints_do_not_pass_unknown():
    """Неизвестные факты не выдаются за соответствующие условиям."""
    ...

def test_foot_route_avoids_barrier():
    """На искусственном графе с преградой пеший путь длиннее прямого."""
    ...

def test_hotelier_reply_does_not_overwrite_conflict():
    """Сохраняются обе версии факта и событие конфликта."""
    ...
```

## 10. Пример расширения одной характеристикой

1. Добавить декларацию в `app/features/registry.yaml`: имя, тип, единицы, scope, alias, source tool, TTL и описание проверок.
2. Если source tool уже существует (например, пешее расстояние до POI), переиспользовать его с другим `poi_type`; не переписывать ranking/UI.
3. Если вычисление принципиально новое (DEM и вид из окна) — написать `app/geo/viewshed.py`, зарегистрировать tool и тест; одного YAML без источника недостаточно.
4. Обновить gold queries и добавить отдельный тест факта с uncertainty/evidence.
