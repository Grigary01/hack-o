"""Whitelist, типизированные аргументы, ограниченный бюджет. Нет eval/getattr по LLM."""
import time
from dataclasses import dataclass
from typing import Callable
from pydantic import Field
from app.schemas.query import Contract


class FeatureToolInput(Contract):
    hotel_id: str
    feature_key: str


@dataclass
class ToolSpec:
    name: str
    handler: Callable
    input_model: type = FeatureToolInput


class ToolRegistry:
    def __init__(self, specs, max_calls=100, deadline_seconds=20):
        self.specs = {s.name:s for s in specs}
        self.remaining = max_calls
        self.deadline = time.monotonic()+deadline_seconds

    def execute(self,name,payload):
        if name not in self.specs:
            raise ValueError(f'Инструмент не разрешён: {name}')
        if self.remaining <= 0 or time.monotonic() >= self.deadline:
            raise TimeoutError('Бюджет локальных инструментов исчерпан')
        self.remaining -= 1
        spec = self.specs[name]
        params = spec.input_model.model_validate(payload)
        # Инструменты локальные и конечные; deadline проверяется между вызовами.
        # Внешние HTTP инструменты используют собственный timeout/retry в адаптерах.
        return spec.handler(params)
