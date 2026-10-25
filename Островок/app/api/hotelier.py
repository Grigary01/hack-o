from fastapi import APIRouter, Depends, Request, HTTPException
from app.api.dependencies import repository
from app.hotelier.dialogue import ask_hotelier, submit_answer, confirm_answer
from app.schemas.hotelier import QuestionRequest, AnswerRequest, ConfirmRequest


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
