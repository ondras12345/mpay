"""allow order with zero amount

Revision ID: 6fb1631eadba
Revises: c7250639e926
Create Date: 2024-11-03 15:42:00.053653

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6fb1631eadba'
down_revision: Union[str, None] = 'c7250639e926'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("standing_orders", schema=None) as batch_op:
        batch_op.drop_constraint("amount_gt_zero", "check")
        batch_op.create_check_constraint("amount_ge_zero", "amount >= 0")


def downgrade() -> None:
    with op.batch_alter_table("standing_orders", schema=None) as batch_op:
        batch_op.drop_constraint("amount_ge_zero", "check")
        batch_op.create_check_constraint("amount_gt_zero", "amount > 0")
