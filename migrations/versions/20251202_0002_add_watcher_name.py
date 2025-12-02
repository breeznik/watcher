"""add watcher name

Revision ID: 20251202_0002
Revises: 20251202_0001
Create Date: 2025-12-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '20251202_0002'
down_revision = '20251202_0001'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite doesn't support ALTER COLUMN, so we need to use batch operations
    with op.batch_alter_table('watchers') as batch_op:
        # Add name column as non-nullable with server_default
        batch_op.add_column(sa.Column('name', sa.String(255), nullable=False, server_default='Unnamed'))
    
    # Update existing rows to use URL substring as name
    conn = op.get_bind()
    conn.execute(text("UPDATE watchers SET name = SUBSTR(url, 1, 50)"))
    
    # Remove server_default after initial population
    with op.batch_alter_table('watchers') as batch_op:
        batch_op.alter_column('name', server_default=None)


def downgrade():
    op.drop_column('watchers', 'name')
