"""initial tables

Revision ID: 20251129_0001
Revises: 
Create Date: 2025-11-29
"""
from alembic import op
import sqlalchemy as sa
from app.db.models import StatusEnum

# revision identifiers, used by Alembic.
revision = '20251129_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    status_enum = sa.Enum(StatusEnum, name="statusenum")
    status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'watchers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('phrase', sa.String(length=255), nullable=False),
        sa.Column('interval_minutes', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('emails', sa.Text(), nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default=sa.sql.expression.true(), nullable=False),
        sa.Column('last_check_at', sa.DateTime(), nullable=True),
        sa.Column('last_status', status_enum, server_default='unknown'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('watcher_id', sa.Integer(), sa.ForeignKey('watchers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('checked_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('status', status_enum, nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_table('logs')
    op.drop_table('watchers')
    sa.Enum(StatusEnum, name='statusenum').drop(op.get_bind(), checkfirst=True)