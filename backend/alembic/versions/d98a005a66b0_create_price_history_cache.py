"""create price history cache (daily_closes, price_history_coverage)

Revision ID: d98a005a66b0
Revises: 4a6e17d63025
Create Date: 2026-10-06 18:00:00.000000

New tables only; nothing existing changes, and both start empty (filled on demand).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd98a005a66b0'
down_revision: Union[str, Sequence[str], None] = '4a6e17d63025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('daily_closes',
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('provider_id', sa.String(length=128), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('close', sa.Numeric(precision=38, scale=18), nullable=False),
    sa.Column('split_factor', sa.Numeric(precision=38, scale=18), server_default='1', nullable=False),
    sa.Column('dividend', sa.Numeric(precision=38, scale=18), server_default='0', nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('provider', 'provider_id', 'day', name=op.f('pk_daily_closes'))
    )
    op.create_table('price_history_coverage',
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('provider_id', sa.String(length=128), nullable=False),
    sa.Column('covered_from', sa.Date(), nullable=True),
    sa.Column('covered_to', sa.Date(), nullable=True),
    sa.Column('checked_to', sa.Date(), nullable=True),
    sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('provider', 'provider_id', name=op.f('pk_price_history_coverage'))
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('price_history_coverage')
    op.drop_table('daily_closes')
