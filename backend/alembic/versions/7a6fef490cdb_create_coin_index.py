"""create coin_index

Revision ID: 7a6fef490cdb
Revises: 1b71b1a9f48d
Create Date: 2026-10-09 14:38:26.801401

New table only, starts empty: the first coin search fills it from CoinGecko. Shared public market
data, no user data; dropping it loses nothing that can't be fetched again.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a6fef490cdb'
down_revision: Union[str, Sequence[str], None] = '1b71b1a9f48d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('coin_index',
    sa.Column('provider_id', sa.String(length=128), nullable=False),
    sa.Column('symbol', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=256), nullable=False),
    sa.Column('market_cap_rank', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('provider_id', name=op.f('pk_coin_index'))
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('coin_index')
