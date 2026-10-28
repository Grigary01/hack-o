"""python -m scripts.migrate_db: backup + проверка старой схемы + upgrade head."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid
from app.core.config import settings
from app.storage.db import open_engine
from app.storage.schema import upgrade_database


def migrate(url):
    engine = open_engine(url)
    backup = None
    try:
        database = engine.url.database
        path = Path(database) if database and database != ':memory:' else None
        if path and path.is_file() and path.stat().st_size:
            directory = path.parent / 'backups'
            directory.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            backup = directory / f'{path.stem}.{stamp}.{uuid.uuid4().hex[:8]}.db'
            with engine.connect() as connection, sqlite3.connect(backup) as target:
                connection.connection.driver_connection.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Резервная копия SQLite не прошла integrity_check')
        revision = upgrade_database(engine)
        return {'revision': revision, 'backup': str(backup) if backup else None}
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', default=settings.database_url)
    args = parser.parse_args()
    print(json.dumps(migrate(args.database_url), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
