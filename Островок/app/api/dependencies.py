from fastapi import Request
from sqlalchemy.orm import Session
from app.storage.repository import Repository


def repository(request: Request):
    with Session(request.app.state.engine) as session, session.begin():
        yield Repository(session)
