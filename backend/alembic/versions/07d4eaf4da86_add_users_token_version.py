"""add users token_version

Revision ID: 07d4eaf4da86
Revises: 7a6fef490cdb
Create Date: 2026-10-24 14:58:31.860077

Adds users.token_version for logout: tokens carry it as their `ver` claim, and logging out bumps
it. Existing rows get 0. Tokens issued before this migration have no `ver` and are rejected, so
everyone logs in once more after the deploy (tokens last at most 30 minutes anyway).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '07d4eaf4da86'
down_revision: Union[str, Sequence[str], None] = '7a6fef490cdb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('token_version', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'token_version')
