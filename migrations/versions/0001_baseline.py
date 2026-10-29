"""Frozen pre-migration SQLite schema (cad3003)."""
from pathlib import Path
from alembic import op

revision = '0001_baseline'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    schema = Path(__file__).resolve().parents[1] / 'legacy_schema.sql'
    for statement in schema.read_text().split(';'):
        if statement.strip():
            op.execute(statement)


def downgrade():
    raise RuntimeError('Восстановите резервную копию; удаление истории не поддерживается')
