"""Question context and last submitted review; preserve all original answers."""
import json
from alembic import op
import sqlalchemy as sa

revision = '0003_question_lifecycle'
down_revision = '0002_conflict_resolutions'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('hotelier_questions', sa.Column('context', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('hotelier_questions', sa.Column('updated_at', sa.String(), nullable=False, server_default=''))
    connection = op.get_bind()
    questions = connection.exec_driver_sql('SELECT id, status, created_at FROM hotelier_questions').all()
    for qid, status, created_at in questions:
        answer = connection.exec_driver_sql(
            'SELECT id, created_at FROM hotelier_answers WHERE question_id = ? '
            'ORDER BY created_at DESC, rowid DESC LIMIT 1', (qid,)).first()
        context = {'reasons': ['unknown'] if status == 'open' else [],
                   'subject_ids': [], 'review_answer_id': answer[0] if answer else None}
        connection.exec_driver_sql('UPDATE hotelier_questions SET context = ?, updated_at = ? WHERE id = ?',
            (json.dumps(context), max(created_at, answer[1]) if answer else created_at, qid))


def downgrade():
    raise RuntimeError('Контекст и история вопросов не удаляются; восстановите резервную копию')
