"""Общий контракт backend/frontend/ML. Не зависит от ORM и HTTP-клиента."""
from typing import Annotated, Literal
from pydantic import AliasChoices, AwareDatetime, Field, StringConstraints
from app.schemas.query import Contract, Value
from app.schemas.hotel import Observation

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ResolveConflictRequest(Contract):
    selected_observation_id: str = Field(min_length=1, validation_alias=AliasChoices('selected_observation_id', 'chosen_observation_id'))
    reason: Reason


class ConflictResolution(ResolveConflictRequest):
    conflict_id: str
    resolved_at: AwareDatetime
    operator_id: str


class Conflict(Contract):
    id: str
    hotel_id: str
    subject_id: str
    feature_key: str
    left_id: str
    right_id: str
    created_at: AwareDatetime
    policy: str = 'withhold_and_ask_hotelier'
    status: Literal['open', 'resolved'] = 'open'
    resolution: ConflictResolution | None = None


class ConflictDetail(Conflict):
    left_observation: Observation
    right_observation: Observation


class CurrentFeature(Contract):
    subject_id: str
    feature_key: str
    value: Value | None = None
    status: Literal['verified', 'estimated', 'unknown', 'conflicted', 'stale']
    observations: list[Observation]
    resolved_conflict_ids: list[str] = Field(default_factory=list)


class ResolveConflictResponse(Contract):
    conflict_id: str
    status: Literal['resolved'] = 'resolved'
    resolution: ConflictResolution
    idempotent: bool
    current: CurrentFeature

    # Совместимость с кабинетом Geo: новое API также возвращает полный current.
    decision_observation_id: str | None = None
    value: Value | None = None
