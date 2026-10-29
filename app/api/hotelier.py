from fastapi import APIRouter, Depends, Request, HTTPException
from dataclasses import asdict
from typing import Literal
from app.api.dependencies import repository
from app.hotelier.dialogue import ask_hotelier, submit_answer, confirm_answer
from app.schemas.hotelier import (QuestionRequest, AnswerRequest, ConfirmRequest, HotelierQuestion,
                                  HotelierAnswer, AnswerConfirmation, ReviewRequest)
from app.schemas.errors import ERROR_RESPONSES
from app.storage.repository import row_dict
from app.schemas.conflicts import ConflictDetail, ResolveConflictRequest, ResolveConflictResponse
from app.features.service import resolve_feature


def demo_only(request:Request):
    if not request.app.state.config.demo_mode:
        raise HTTPException(403,'Локальный кабинет — только симулятор; реальная авторизация пока не реализована')


router = APIRouter(prefix='/api/hotelier',tags=['hotelier demo'],dependencies=[Depends(demo_only)],
                   responses=ERROR_RESPONSES)


@router.get('/conflicts', response_model=list[ConflictDetail])
def conflicts(hotel_id: str | None = None, status: Literal['open', 'resolved'] | None = None,
              repo=Depends(repository)):
    if hotel_id is not None:
        repo.hotel(hotel_id)
    return repo.conflict_details(hotel_id, status)


@router.post('/conflicts/{conflict_id}/resolve', response_model=ResolveConflictResponse)
def resolve_conflict(conflict_id: str, payload: ResolveConflictRequest, repo=Depends(repository)):
    """Одно решение оператора на конфликт; повтор с тем же выбором идемпотентен, другой выбор — 409.

    review:* (номер против расчёта по зданию, поправка отельера к расчёту) дополнительно
    сохраняет свидетельство operator_decision: его учитывают поиск и кабинет.
    """
    conflict = repo.conflict(conflict_id)
    if conflict['policy'].startswith('review:') and repo.conflict_resolution(conflict_id) is None:
        from app.hotelier.review import record_operator_decision
        # Сначала проверяем выбор (422/404), затем пишем решение и свидетельство атомарно.
        repo.resolve_conflict(conflict_id, payload.selected_observation_id, payload.reason)
        record_operator_decision(repo, conflict_id, payload.selected_observation_id, payload.reason)
        resolution, idempotent = repo.conflict_resolution(conflict_id), False
    else:
        resolution, idempotent = repo.resolve_conflict(
            conflict_id, payload.selected_observation_id, payload.reason)
    records = repo.conflict_records()
    conflict = next(c for c in records if c.id == conflict_id)
    current = resolve_feature(repo.observations(conflict.hotel_id), conflict.subject_id,
        conflict.feature_key, include_simulated=True, conflicts=records)
    return {'conflict_id': conflict_id, 'resolution': resolution,
            'idempotent': idempotent, 'current': asdict(current)}


@router.get('/questions', response_model=list[HotelierQuestion])
def questions(hotel_id: str | None = None, status: Literal['open', 'answered'] | None = None,
              repo=Depends(repository)):
    return repo.questions(hotel_id=hotel_id, status=status)


@router.post('/questions', response_model=HotelierQuestion)
def create_question(payload:QuestionRequest,repo=Depends(repository)):
    return ask_hotelier(repo,payload.hotel_id,payload.feature_key)


@router.post('/questions/{qid}/answer', response_model=HotelierAnswer)
def answer(qid:str,payload:AnswerRequest,request:Request,repo=Depends(repository)):
    return submit_answer(repo,qid,payload.text,reply_parser=request.app.state.reply_parser)


@router.get('/answers/{aid}', response_model=HotelierAnswer)
def saved_answer(aid: str, repo=Depends(repository)):
    return row_dict(repo.answer(aid))


@router.post('/answers/{aid}/confirm', response_model=AnswerConfirmation)
def confirm(aid:str,payload:ConfirmRequest,repo=Depends(repository)):
    return confirm_answer(repo,aid,payload.accept)


@router.get('/hotels/{hotel_id}/facts')
def facts(hotel_id:str,repo=Depends(repository)):
    from app.hotelier.review import hotel_facts
    return {'facts':hotel_facts(repo,hotel_id),'conflicts':repo.conflicts(hotel_id)}


@router.post('/facts/review')
def review(payload:ReviewRequest,repo=Depends(repository)):
    from app.hotelier.review import review_fact
    return review_fact(repo,payload.hotel_id,payload.feature_key,payload.verdict,payload.value,payload.comment)

