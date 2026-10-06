"""create user_assets (what each user's ticker means)

Revision ID: 4a6e17d63025
Revises: ec96ddc15af2
Create Date: 2026-10-06 16:00:00.000000

Backfill, with no network calls: one row per (user, symbol) that has transactions. The asset
type is the latest trade's (what the app already used to pick a provider), and the coin is left
unknown (provider_id NULL), so existing crypto positions keep being priced by the automatic
coin rules, with the "picked automatically" disclosure, until the user picks a coin.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a6e17d63025'
down_revision: Union[str, Sequence[str], None] = 'ec96ddc15af2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('user_assets',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('asset_type', sa.Enum('stock', 'crypto', name='asset_type', native_enum=False, create_constraint=False, length=16), nullable=False),
    sa.Column('provider_id', sa.String(length=128), nullable=True),
    sa.Column('id_source', sa.String(length=8), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("asset_type IN ('stock', 'crypto')", name=op.f('ck_user_assets_asset_type')),
    sa.CheckConstraint("id_source IN ('user', 'rule')", name=op.f('ck_user_assets_id_source')),
    sa.CheckConstraint('(provider_id IS NULL) = (id_source IS NULL)', name=op.f('ck_user_assets_provider_id_source')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_assets_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'symbol', name=op.f('pk_user_assets'))
    )
    # Latest trade per (user, symbol), ties broken by insertion time, as the app did before.
    op.execute(
        """
        INSERT INTO user_assets (user_id, symbol, asset_type)
        SELECT DISTINCT ON (user_id, symbol) user_id, symbol, asset_type
        FROM transactions
        ORDER BY user_id, symbol, executed_at DESC, created_at DESC
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('user_assets')
