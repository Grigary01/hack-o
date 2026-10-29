"""Ответы API поверх существующих фактов и ML-контрактов."""
from typing import Literal
from app.schemas.query import Contract
from app.schemas.hotel import Hotel, Observation
from app.schemas.conflicts import Conflict, CurrentFeature


class HotelDetail(Contract):
    hotel: Hotel
    observations: list[Observation]
    conflicts: list[Conflict]


class HotelEvidence(Contract):
    observations: list[Observation]
    conflicts: list[Conflict]
    current_real: list[CurrentFeature]
    current_demo: list[CurrentFeature]


class HealthResponse(Contract):
    status: Literal['ok', 'needs_seed']
    database: Literal['ok']
    hotels: int
    parser_mode: str
    # Какая языковая модель разбирает запросы: «облако: claude-opus-5», «локально: gemma3:12b», «нет».
    llm: str | None = None
    reply_parser_mode: str
    demo_mode: bool
    external_services_checked: Literal[False] = False
