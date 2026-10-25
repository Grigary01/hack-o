"""Новая boolean room-характеристика подключается YAML через provider=hotelier."""
from functools import lru_cache
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.core.config import settings


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

    @model_validator(mode='after')
    def coherent(self):
        if self.type == 'category' and not self.choices:
            raise ValueError('category требует choices')
        if self.provider == 'hotelier' and (self.type != 'boolean' or self.scope != 'room' or not self.question):
            raise ValueError('MVP hotelier provider требует boolean, room и question')
        return self


class FeatureRegistry:
    def __init__(self, path: Path = settings.registry_path):
        raw = yaml.safe_load(path.read_text())
        self.definitions = {key: FeatureDefinition.model_validate(value) for key, value in raw.items()}

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
