"""create watchlist_items

Revision ID: 1b71b1a9f48d
Revises: d98a005a66b0
Create Date: 2026-10-07 10:00:00.000000

New table only, starts empty. Each row points at the user's user_assets record for the symbol,
which stays the only place a symbol's meaning (asset type, coin) is stored.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b71b1a9f48d'
down_revision: Union[str, Sequence[str], None] = 'd98a005a66b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('watchlist_items',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id', 'symbol'], ['user_assets.user_id', 'user_assets.symbol'], name='fk_watchlist_items_user_assets'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_watchlist_items_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'symbol', name=op.f('pk_watchlist_items'))
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('watchlist_items')
