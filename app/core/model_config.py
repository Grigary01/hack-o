"""Загрузка общей ML-конфигурации без сети и секретов.

ML-участник меняет config/models.yaml; backend получает проверенные значения.
Опечатка или недопустимый параметр останавливают запуск с понятной ошибкой,
а не переключают приложение незаметно на другую модель.
"""
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    parser_mode: Literal['ollama', 'groq', 'offline', 'fixture']
    model_name: str = Field(min_length=1)
    groq_model: str = Field(min_length=1)
    temperature: float = Field(ge=0, le=2)
    max_output_tokens: int = Field(gt=0)
    ollama_num_ctx: int = Field(gt=0)
    parser_timeout_seconds: float = Field(gt=0)
    groq_reasoning_effort: Literal['low', 'medium', 'high']


def load_model_config(path: Path) -> ModelConfig:
    try:
        return ModelConfig.model_validate(yaml.safe_load(path.read_text(encoding='utf-8')))
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ValueError(f'Проверьте ML-конфигурацию {path}: {exc}') from exc
