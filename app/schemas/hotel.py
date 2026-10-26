from datetime import datetime
from typing import Literal
from pydantic import Field, AwareDatetime, model_validator
from app.schemas.query import Contract, Value
from app.features.registry import get_registry


class Source(Contract):
    type: Literal['openstreetmap', 'geo_model', 'hotelier', 'hotelier_simulated']
    name: str
    ref: str
    url: str | None = None


class Evidence(Contract):
    source: Source
    method: str
    raw_excerpt: str = ''
    snapshot_path: str | None = None
    details: dict = Field(default_factory=dict)


class Observation(Contract):
    id: str
    hotel_id: str
    subject_type: Literal['hotel', 'room']
    subject_id: str
    feature_key: str
    value: Value | None
    unit: str | None = None
    observed_at: AwareDatetime
    collected_at: AwareDatetime
    expires_at: AwareDatetime
    status: Literal['verified', 'estimated', 'unknown', 'conflicted', 'stale']
    confidence_level: Literal['high', 'medium', 'low', 'unknown']
    confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_method: str = Field(min_length=1)
    quality_flags: list[str] = Field(default_factory=list)
    evidence: Evidence

    @model_validator(mode='after')
    def coherent(self):
        reg = get_registry()
        definition = reg.get(self.feature_key)
        reg.validate_value(self.feature_key, self.value, allow_null=True)
        if self.subject_type != definition.scope or self.unit != definition.unit:
            raise ValueError('Observation scope/unit не совпадает с registry')
        if self.expires_at <= self.observed_at:
            raise ValueError('TTL должен быть положительным')
        if self.value is None and self.status not in ('unknown', 'stale'):
            raise ValueError('Пустое значение должно быть unknown/stale')
        return self


class Hotel(Contract):
    id: str
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    region: str = 'Adler'
    tags: dict[str, str] = Field(default_factory=dict)
    source_url: str
    collected_at: AwareDatetime
