"""add invites system

Revision ID: 0054
Revises: 0053
Create Date: 2026-04-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0054'
down_revision: Union[str, None] = '0053'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поля к users
    op.add_column(
        'users',
        sa.Column('invite_activated', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column(
        'users',
        sa.Column('is_permanent', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column(
        'users',
        sa.Column('is_banned', sa.Boolean(), nullable=False, server_default='false'),
    )

    # Создаём таблицу invites
    op.create_table(
        'invites',
        sa.Column('code', sa.String(16), primary_key=True),
        sa.Column(
            'created_by',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'used_by',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
    )

    op.create_index('ix_invites_created_by', 'invites', ['created_by'])
    op.create_index('ix_invites_used_by', 'invites', ['used_by'])


def downgrade() -> None:
    op.drop_index('ix_invites_used_by', table_name='invites')
    op.drop_index('ix_invites_created_by', table_name='invites')
    op.drop_table('invites')
    op.drop_column('users', 'is_banned')
    op.drop_column('users', 'is_permanent')
    op.drop_column('users', 'invite_activated')
