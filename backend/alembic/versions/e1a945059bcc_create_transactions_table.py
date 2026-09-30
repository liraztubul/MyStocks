"""create transactions table

Revision ID: e1a945059bcc
Revises: 8f06dfd7d5f9
Create Date: 2026-09-30 16:40:45.802250

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a945059bcc'
down_revision: Union[str, Sequence[str], None] = '8f06dfd7d5f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Enum CHECKs are declared explicitly below; create_constraint=False stops sa.Enum
    # from emitting a second, duplicate copy of each.
    op.create_table('transactions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('symbol', sa.String(length=32), nullable=False),
    sa.Column('asset_type', sa.Enum('stock', 'crypto', name='asset_type', native_enum=False, create_constraint=False, length=16), nullable=False),
    sa.Column('side', sa.Enum('buy', 'sell', name='side', native_enum=False, create_constraint=False, length=16), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=28, scale=10), nullable=False),
    sa.Column('price', sa.Numeric(precision=28, scale=10), nullable=False),
    sa.Column('fee', sa.Numeric(precision=28, scale=10), server_default='0', nullable=False),
    sa.Column('currency', sa.String(length=3), server_default='USD', nullable=False),
    sa.Column('executed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("asset_type IN ('stock', 'crypto')", name=op.f('ck_transactions_asset_type')),
    sa.CheckConstraint("side IN ('buy', 'sell')", name=op.f('ck_transactions_side')),
    sa.CheckConstraint('fee >= 0', name=op.f('ck_transactions_fee_non_negative')),
    sa.CheckConstraint('price > 0', name=op.f('ck_transactions_price_positive')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_transactions_quantity_positive')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_transactions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_transactions'))
    )
    op.create_index('ix_transactions_user_id_symbol', 'transactions', ['user_id', 'symbol'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_transactions_user_id_symbol', table_name='transactions')
    op.drop_table('transactions')
