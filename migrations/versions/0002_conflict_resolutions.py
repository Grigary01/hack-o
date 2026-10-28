"""Append-only decisions; original conflicts and observations remain intact."""
from alembic import op
import sqlalchemy as sa

revision = '0002_conflict_resolutions'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('conflict_resolutions',
        sa.Column('conflict_id', sa.String(), sa.ForeignKey('conflicts.id'), primary_key=True),
        sa.Column('selected_observation_id', sa.String(), sa.ForeignKey('observations.id'), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('resolved_at', sa.String(), nullable=False),
        sa.Column('operator_id', sa.String(), nullable=False),
    )


def downgrade():
    raise RuntimeError('Решения не удаляются автоматически; восстановите резервную копию')
