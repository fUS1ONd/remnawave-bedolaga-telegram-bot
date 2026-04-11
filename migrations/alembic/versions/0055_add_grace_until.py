"""add grace_until to users

Revision ID: 0055
Revises: 0054
Create Date: 2026-04-11
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = '0055'
down_revision: Union[str, None] = '0054'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('grace_until', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('users', 'grace_until')
