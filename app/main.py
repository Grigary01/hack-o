"""FastAPI composition root. Не выгружает OSM и не заполняет demo при импорте."""
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.config import settings
from app.storage.db import create_db
from app.api.dependencies import repository
from app.api import search, hotels, hotelier, environment
from app.ml.query_parser import make_parser, ParserError, QueryParserUnavailable
from app.core.errors import StateConflictError, NotFoundError, ReplyParserError, ReplyParserUnavailable
from app.hotelier.reply_parser import make_reply_parser
from app.schemas.errors import APIError, ERROR_RESPONSES
from app.schemas.hotel_views import HealthResponse


def error_response(status, code, detail, headers=None):
    return JSONResponse(status_code=status, headers=headers,
                        content=APIError(code=code, detail=detail).model_dump(mode='json'))


def create_app(engine=None,parser=None,config=settings,*,reply_parser=None):
    api = FastAPI(title='О!дин шаг · Адлер',version='0.1.0',
                  description='Доказательный подбор; локальный демонстрационный кабинет отельера.')
    api.state.engine = engine if engine is not None else create_db(config.database_url)
    api.state.parser = parser or make_parser(config)
    api.state.reply_parser = reply_parser if reply_parser is not None else make_reply_parser(config)
    api.state.config = config
    api.include_router(search.router)
    api.include_router(hotels.router)
    api.include_router(hotelier.router)
    api.include_router(environment.router)

    @api.exception_handler(RequestValidationError)
    async def request_invalid(request: Request, exc: RequestValidationError):
        return error_response(422, 'invalid_request', jsonable_encoder(exc.errors()))

    @api.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        code = {403: 'forbidden', 404: 'not_found', 409: 'state_conflict',
                422: 'invalid_request', 502: 'invalid_model_output', 503: 'service_unavailable'}.get(
                    exc.status_code, 'http_error')
        return error_response(exc.status_code, code, exc.detail, exc.headers)

    @api.exception_handler(ReplyParserError)
    async def reply_parser_error(request: Request, exc: ReplyParserError):
        unavailable = isinstance(exc, ReplyParserUnavailable)
        return error_response(503 if unavailable else 502,
                              'service_unavailable' if unavailable else 'invalid_model_output', str(exc))

    @api.exception_handler(StateConflictError)
    async def state_conflict(request: Request, exc: StateConflictError):
        return error_response(409, 'state_conflict', str(exc))

    @api.exception_handler(NotFoundError)
    async def missing(request:Request,exc:NotFoundError):
        return error_response(404, 'not_found', str(exc))

    @api.exception_handler(ValueError)
    async def invalid(request:Request,exc:ValueError):
        if isinstance(exc, QueryParserUnavailable):
            return error_response(503, 'service_unavailable', str(exc))
        if isinstance(exc, ParserError):
            return error_response(502, 'invalid_model_output', str(exc))
        return error_response(422, 'invalid_request', str(exc))

    @api.get('/api/health', response_model=HealthResponse, responses=ERROR_RESPONSES)
    def health(repo=Depends(repository)):
        count = len(repo.hotels())
        return {'status':'ok' if count else 'needs_seed','database':'ok','hotels':count,
                'parser_mode':api.state.parser.mode,'reply_parser_mode':getattr(api.state.reply_parser,'mode','injected'),
                'demo_mode':config.demo_mode,
                'external_services_checked':False}

    return api


app = create_app()
