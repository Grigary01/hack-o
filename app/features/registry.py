"""Новая boolean room-характеристика подключается YAML через provider=hotelier.

companions: какие расчётные характеристики поиск добавляет к желанию гостя
(«вид на море» → ещё и расчётный вид из окон здания). model_check: с какими
расчётами сверять ответ отельера. Оба поля описываются только в YAML.
"""
from functools import lru_cache
from pathlib import Path
import re
from typing import Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.core.config import settings


class Companion(BaseModel):
    """Расчётная характеристика-спутник. desired — для любого желания родителя;
    desired_if_true/false — для boolean-родителя («с видом» / «без вида»)."""
    model_config = ConfigDict(extra='forbid')
    feature_key: str
    desired: str | bool | int | float | None = None
    desired_if_true: str | bool | int | float | None = None
    desired_if_false: str | bool | int | float | None = None
    weight_factor: float = Field(default=1., gt=0, le=1)


class ModelCheck(BaseModel):
    """Сверка утверждения отельера о номере с расчётом по зданию."""
    model_config = ConfigDict(extra='forbid')
    potential: str
    none_value: str
    min_floor: str | None = None


class FeatureDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str
    description: str
    type: Literal['number', 'boolean', 'category']
    unit: str | None = None
    scope: Literal['hotel', 'room']
    provider: str
    ttl_days: int = Field(gt=0, le=3650)
    default_weight: float = Field(ge=0, le=1)
    aliases: list[str] = Field(default_factory=list)
    choices: list[str] = Field(default_factory=list)
    question: str | None = None
    scale: float = Field(default=1000, gt=0)
    ordinal: bool = False  # choices упорядочены: соседние значения частично совпадают
    choice_labels: dict[str, str] = Field(default_factory=dict)
    companions: list[Companion] = Field(default_factory=list)
    model_check: ModelCheck | None = None
    # Офлайн-разбор свободного запроса (app/ml/rules_parser.py). Регулярные выражения
    # по основам слов; negative — слова противоположного смысла («шумный» для тишины).
    query_patterns: list[str] = Field(default_factory=list)
    query_negative_patterns: list[str] = Field(default_factory=list)
    query_desired: str | bool | None = None
    # True: отрицание не переворачивает желание («без подъёмов» — тоже поменьше подъёмов).
    query_negation_keeps: bool = False
    # Текстовая подсказка LLM-парсеру: как гости называют признак и как заполнить desired.
    # Только признаки с подсказкой попадают в промпт и enum схемы LLM: расчётные
    # спутники (*_potential, *_min_floor) модель не выводит, их добавляет backend.
    query_hint: str | None = None

    @model_validator(mode='after')
    def coherent(self):
        if self.type == 'category' and not self.choices:
            raise ValueError('category требует choices')
        if self.provider == 'hotelier' and (self.type != 'boolean' or self.scope != 'room' or not self.question):
            raise ValueError('MVP hotelier provider требует boolean, room и question')
        if set(self.choice_labels) - set(self.choices):
            raise ValueError('choice_labels для несуществующих choices')
        for pattern in self.query_patterns + self.query_negative_patterns:
            re.compile(pattern)
        if self.query_patterns and self.query_desired is None:
            raise ValueError('query_patterns требуют query_desired')
        return self

    def display(self, value):
        """Значение для человека: «широкий» вместо wide."""
        if isinstance(value, bool):
            return 'да' if value else 'нет'
        return self.choice_labels.get(value, str(value)) if isinstance(value, str) else value


class FeatureRegistry:
    def __init__(self, path: Path = settings.registry_path):
        raw = yaml.safe_load(path.read_text())
        self.definitions = {key: FeatureDefinition.model_validate(value) for key, value in raw.items()}
        # Ссылки между характеристиками проверяем сразу, а не при первом поиске.
        for key, definition in self.definitions.items():
            for companion in definition.companions:
                target = self.get(companion.feature_key)
                if target.scope != 'hotel' or target.provider == 'hotelier':
                    raise ValueError(f'{key}: спутник {companion.feature_key} должен быть расчётным и про отель')
                for value in (companion.desired, companion.desired_if_true, companion.desired_if_false):
                    if value is not None and not (target.type == 'number' and value in ('near', 'far')):
                        self.validate_value(companion.feature_key, value)
            check = definition.model_check
            if check:
                self.validate_value(check.potential, check.none_value)
                if check.min_floor:
                    self.get(check.min_floor)

    def get(self, key: str) -> FeatureDefinition:
        if key not in self.definitions:
            raise ValueError(f'Неизвестная характеристика: {key}')
        return self.definitions[key]

    def validate_value(self, key, value, *, allow_null=False):
        definition = self.get(key)
        if value is None and allow_null:
            return
        valid = ((definition.type == 'boolean' and type(value) is bool) or
                 (definition.type == 'number' and type(value) in (int, float) and value >= 0) or
                 (definition.type == 'category' and value in definition.choices))
        if not valid:
            raise ValueError(f'Недопустимое значение {key}: {value!r}')


@lru_cache
def get_registry():
    return FeatureRegistry(settings.registry_path)
