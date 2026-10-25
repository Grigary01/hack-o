from pydantic import Field, StrictBool
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
