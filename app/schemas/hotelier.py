from typing import Literal
from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr
from app.schemas.query import Contract


class RoomClaim(Contract):
    room_number: str = Field(pattern=r'^\d{1,5}$')
    floor: int | None = Field(default=None,ge=-5,le=100)
    feature_key: str
    value: StrictBool
    quote: str


class ReplyExtraction(Contract):
    claims: list[RoomClaim] = Field(default_factory=list,max_length=50)
    unparsed: list[str] = Field(default_factory=list)
    parser_mode: str = 'bounded_rules'


class QuestionRequest(Contract):
    hotel_id: str
    feature_key: str


class AnswerRequest(Contract):
    text: str = Field(min_length=1,max_length=3000)


class ConfirmRequest(Contract):
    accept: bool


class ReviewRequest(Contract):
    """Отельер подтверждает или исправляет расчётный факт об отеле."""
    hotel_id: str
    feature_key: str
    verdict: Literal['confirm', 'correct']
    value: StrictBool | StrictInt | StrictFloat | StrictStr | None = None
    comment: str = Field(default='', max_length=1000)


class ResolveRequest(Contract):
    """Оператор выбирает одну из версий конфликта и объясняет почему."""
    chosen_observation_id: str
    reason: str = Field(min_length=3, max_length=1000)
