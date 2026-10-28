from typing import Literal
from pydantic import Field, model_validator
from app.schemas.query import Contract, ParsedHotelQuery
from app.schemas.hotel import Hotel, Observation


class ParseRequest(Contract):
    text: str = Field(min_length=1,max_length=2000)


class SearchRequest(Contract):
    text: str | None = Field(default=None,min_length=1,max_length=2000)
    parsed: ParsedHotelQuery | None = None
    weights: dict[str,float] = Field(default_factory=dict)
    include_simulated: bool = False
    ranking_method: Literal['weighted_v1','balanced_v2'] = 'balanced_v2'
    balance: float = Field(default=.25,ge=0,le=1)

    @model_validator(mode='after')
    def input_contract(self):
        if (self.text is None) == (self.parsed is None):
            raise ValueError('Передайте ровно одно поле: text или parsed')
        if any(not 0 <= w <= 1 for w in self.weights.values()):
            raise ValueError('Веса должны быть от 0 до 1')
        return self


class CriterionResult(Contract):
    feature_key: str
    requested: str
    actual: object = None
    outcome: Literal['matched','violated','unknown','preference']
    status: str
    subject_id: str | None = None
    match: float | None = None
    explanation: str
    evidence: list[Observation] = Field(default_factory=list)


class HotelSearchResult(Contract):
    hotel: Hotel
    eligible: bool | None
    recommended_room_id: str | None = None
    score: float | None
    coverage: float
    ranking_score: float
    uncertainty: float
    criteria: list[CriterionResult]
    warnings: list[str] = Field(default_factory=list)
    pending_hotelier_question_ids: list[str] = Field(default_factory=list)
    ranking_method: str = 'weighted_v1'
    ranking_interval: tuple[float,float] | None = None
    group_scores: list[dict] = Field(default_factory=list)
    pareto_dominated: bool = False


class SearchResponse(Contract):
    parsed: ParsedHotelQuery
    parser_mode: str
    status: Literal['ok','needs_clarification'] = 'ok'
    matched: list[HotelSearchResult] = Field(default_factory=list)
    needs_verification: list[HotelSearchResult] = Field(default_factory=list)
    excluded: list[HotelSearchResult] = Field(default_factory=list)
    trace: list[dict] = Field(default_factory=list)
    include_simulated: bool = False
    ranking_method: str = 'weighted_v1'
    balance: float = Field(default=.25,ge=0,le=1)
