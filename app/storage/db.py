from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool
from app.storage.schema import ensure_schema


def open_engine(url):
    parsed = make_url(url)
    if parsed.get_backend_name() != 'sqlite':
        raise ValueError('В MVP поддерживается SQLite')
    memory = parsed.database in (None, '', ':memory:')
    if not memory:
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={'check_same_thread':False, 'timeout':15},
                           **({'poolclass':StaticPool} if memory else {}))

    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')

    return engine


def create_db(url):
    engine = open_engine(url)
    try:
        ensure_schema(engine)
    except Exception:
        engine.dispose()
        raise
    return engine
