"""add email tracking to logs

Revision ID: 20251202_0001
Revises: 20251129_0001
Create Date: 2025-12-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251202_0001'
down_revision = '20251129_0001'
branch_labels = None
depends_on = None


def upgrade():
    # Add email_sent column with default False
    op.add_column('logs', sa.Column('email_sent', sa.Boolean(), nullable=False, server_default='0'))
    # Add email_error column
    op.add_column('logs', sa.Column('email_error', sa.Text(), nullable=True))


def downgrade():
    # Remove the columns
    op.drop_column('logs', 'email_error')
    op.drop_column('logs', 'email_sent')
