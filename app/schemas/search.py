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
    # Уточнение расплывчатого пожелания без нового разбора текста: {"window_view": "sea"}.
    # "any" — оставить «любой из». Ключи — понятия из app/features/concepts.yaml.
    choices: dict[str,str] = Field(default_factory=dict)

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
    model_conflicts: list[dict] = Field(default_factory=list)


class NeedResult(Contract):
    """Что нашлось по одной части запроса гостя у этого отеля."""
    quote: str
    kind: Literal['feature','any_of','unsupported']
    outcome: Literal['matched','partial','unknown','violated','unchecked']
    text: str
    # Объяснение расчёта по-человечески, если есть («Море: широкий вид из окон стороны З, с 3-го этажа»).
    detail: str | None = None
    features: list[str] = Field(default_factory=list)
    # Для any_of — какой вариант дал лучший результат (ключ понятия и признак).
    best_option: str | None = None
    best_feature: str | None = None


class HotelSearchResult(Contract):
    hotel: Hotel
    eligible: bool | None
    recommended_room_id: str | None = None
    score: float | None
    coverage: float
    ranking_score: float
    uncertainty: float
    criteria: list[CriterionResult]
    needs: list[NeedResult] = Field(default_factory=list)
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
