"""FastAPI composition root. Не выгружает OSM и не заполняет demo при импорте."""
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.storage.db import create_db
from app.api.dependencies import repository
from app.api import search, hotels, hotelier
from app.ml.query_parser import make_parser, ParserError


def create_app(engine=None,parser=None,config=settings):
    api = FastAPI(title='О!дин шаг · Адлер',version='0.1.0',
                  description='Доказательный подбор; локальный демонстрационный кабинет отельера.')
    api.state.engine = engine if engine is not None else create_db(config.database_url)
    api.state.parser = parser or make_parser(config)
    api.state.config = config
    api.include_router(search.router)
    api.include_router(hotels.router)
    api.include_router(hotelier.router)

    @api.exception_handler(LookupError)
    async def missing(request:Request,exc:LookupError):
        return JSONResponse(status_code=404,content={'detail':str(exc)})

    @api.exception_handler(ValueError)
    async def invalid(request:Request,exc:ValueError):
        return JSONResponse(status_code=502 if isinstance(exc,ParserError) else 422,
                            content={'detail':str(exc)})

    @api.get('/api/health')
    def health(repo=Depends(repository)):
        count = len(repo.hotels())
        return {'status':'ok' if count else 'needs_seed','database':'ok','hotels':count,
                'parser_mode':api.state.parser.mode,'demo_mode':config.demo_mode,
                'external_services_checked':False}

    return api


app = create_app()
