from fastapi import APIRouter, Depends, Request, HTTPException
from app.api.dependencies import repository
from app.hotelier.dialogue import ask_hotelier, submit_answer, confirm_answer
from app.schemas.hotelier import QuestionRequest, AnswerRequest, ConfirmRequest, ReviewRequest, ResolveRequest


def demo_only(request:Request):
    if not request.app.state.config.demo_mode:
        raise HTTPException(403,'Локальный кабинет — только симулятор; реальная авторизация пока не реализована')


router = APIRouter(prefix='/api/hotelier',tags=['hotelier demo'],dependencies=[Depends(demo_only)])


@router.get('/questions')
def questions(repo=Depends(repository)):
    return repo.questions()


@router.post('/questions')
def create_question(payload:QuestionRequest,repo=Depends(repository)):
    return ask_hotelier(repo,payload.hotel_id,payload.feature_key)


@router.post('/questions/{qid}/answer')
def answer(qid:str,payload:AnswerRequest,repo=Depends(repository)):
    return submit_answer(repo,qid,payload.text)


@router.post('/answers/{aid}/confirm')
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


@router.post('/conflicts/{conflict_id}/resolve')
def resolve(conflict_id:str,payload:ResolveRequest,repo=Depends(repository)):
    from app.hotelier.review import resolve_conflict
    return resolve_conflict(repo,conflict_id,payload.chosen_observation_id,payload.reason)
