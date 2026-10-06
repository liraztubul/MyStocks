"""users.email is always lowercase

Revision ID: ec96ddc15af2
Revises: e1a945059bcc
Create Date: 2026-10-06 14:30:00.000000

The API has always lowercased emails, so this should find nothing to change. If a mixed-case
row exists anyway (inserted outside the API), it is lowercased: login lowercases its input, so
such an account could not log in before. Two rows that differ only by case can't be merged
safely, so the migration stops and asks for a manual decision instead.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ec96ddc15af2'
down_revision: Union[str, Sequence[str], None] = 'e1a945059bcc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    duplicates = conn.execute(
        sa.text("SELECT lower(email) FROM users GROUP BY lower(email) HAVING count(*) > 1")
    ).scalars().all()
    if duplicates:
        raise RuntimeError(
            f"{len(duplicates)} email address(es) are registered more than once with different "
            "letter case; resolve them by hand before running this migration."
        )
    conn.execute(sa.text("UPDATE users SET email = lower(email) WHERE email <> lower(email)"))
    op.create_check_constraint(op.f('ck_users_email_lowercase'), 'users', 'email = lower(email)')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_users_email_lowercase'), 'users', type_='check')
