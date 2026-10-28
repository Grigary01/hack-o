"""Connection/transaction принадлежат проверяющему wrapper в app.storage.schema."""
from alembic import context
from app.storage.models import Base

connection = context.config.attributes.get('connection')
if connection is None:
    raise RuntimeError('Используйте python -m scripts.migrate_db (проверка схемы и резервная копия)')
context.configure(connection=connection, target_metadata=Base.metadata)
with context.begin_transaction():
    context.run_migrations()
