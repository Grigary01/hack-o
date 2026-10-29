from typing import Literal
from pydantic import AwareDatetime, Field, StrictBool, StrictFloat, StrictInt, StrictStr
from app.schemas.query import Contract
from app.schemas.conflicts import Conflict


class RoomClaim(Contract):
    room_number: str = Field(pattern=r'^\d{1,5}$')
    floor: StrictInt | None = Field(default=None,ge=-5,le=100)
    feature_key: str = Field(min_length=1)
    value: StrictBool
    quote: str = Field(min_length=1,max_length=3000)


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
    accept: StrictBool


class QuestionContext(Contract):
    reasons: list[Literal['unknown', 'stale', 'conflicted', 'pending_answer',
                          'unparsed_answer', 'rejected_answer']] = Field(default_factory=list)
    subject_ids: list[str] = Field(default_factory=list)
    review_answer_id: str | None = None


class HotelierQuestion(Contract):
    id: str
    hotel_id: str
    feature_key: str
    text: str
    status: Literal['open', 'answered']
    created_at: AwareDatetime
    context: QuestionContext
    updated_at: AwareDatetime


class HotelierAnswer(Contract):
    id: str
    question_id: str
    text: str
    extraction: ReplyExtraction
    status: Literal['pending', 'confirmed', 'rejected']
    simulated: bool
    created_at: AwareDatetime


class ModelReview(Contract):
    room_id: str
    reason: Literal['model_sees_none', 'below_model_min_floor']
    text: str
    hotelier_observation_id: str
    model_observation_id: str


class AnswerConfirmation(Contract):
    answer_id: str
    status: Literal['confirmed', 'rejected']
    idempotent: bool
    observation_ids: list[str]
    conflicts: list[Conflict]
    source_type: Literal['hotelier_simulated'] | None
    question: HotelierQuestion
    # Расхождения ответа о номере с расчётом по зданию (registry.model_check).
    model_review: list[ModelReview] = Field(default_factory=list)


class ReviewRequest(Contract):
    """Отельер подтверждает или исправляет расчётный факт об отеле."""
    hotel_id: str
    feature_key: str
    verdict: Literal['confirm', 'correct']
    value: StrictBool | StrictInt | StrictFloat | StrictStr | None = None
    comment: str = Field(default='', max_length=1000)
