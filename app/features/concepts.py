"""Словарь расплывчатых пожеланий («вид из окна») → «любой из» признаков реестра.

Как и registry.yaml, понятия описываются текстом: новое понятие не требует кода.
Ссылки на признаки и их значения проверяются при загрузке.
"""
from functools import lru_cache
from pathlib import Path
import re
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.features.registry import get_registry

CONCEPTS_PATH = Path(__file__).with_name('concepts.yaml')


class ConceptOption(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: str = Field(pattern=r'^[a-z_]+$')
    label: str
    feature_key: str
    desired: str | bool | int | float


class Concept(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str
    question: str
    default_weight: float = Field(ge=0, le=1)
    hint: str
    patterns: list[str] = Field(default_factory=list)
    options: list[ConceptOption] = Field(min_length=2)

    @model_validator(mode='after')
    def coherent(self):
        registry = get_registry()
        keys = [o.key for o in self.options]
        if len(set(keys)) != len(keys) or 'any' in keys:
            raise ValueError('Ключи вариантов уникальны; any зарезервирован для «любой»')
        for option in self.options:
            definition = registry.get(option.feature_key)
            if definition.scope != 'hotel':
                raise ValueError(f'{option.feature_key}: вариант понятия должен быть признаком отеля')
            registry.validate_value(option.feature_key, option.desired)
        for pattern in self.patterns:
            re.compile(pattern)
        return self

    def option(self, key: str) -> ConceptOption:
        for option in self.options:
            if option.key == key:
                return option
        raise ValueError(f'Неизвестный вариант «{key}» для «{self.label}»')


@lru_cache
def get_concepts() -> dict[str, Concept]:
    raw = yaml.safe_load(CONCEPTS_PATH.read_text()) or {}
    return {key: Concept.model_validate(value) for key, value in raw.items()}


def get_concept(key: str) -> Concept:
    concepts = get_concepts()
    if key not in concepts:
        raise ValueError(f'Неизвестное понятие: {key}')
    return concepts[key]
