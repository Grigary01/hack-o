from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from app.storage.models import Base


def create_db(url):
    if not url.startswith('sqlite:'):
        raise ValueError('В MVP поддерживается SQLite')
    if url not in ('sqlite://', 'sqlite:///:memory:'):
        Path(url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={'check_same_thread':False, 'timeout':15},
                           **({'poolclass':StaticPool} if url in ('sqlite://','sqlite:///:memory:') else {}))

    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')

    Base.metadata.create_all(engine)
    return engine
