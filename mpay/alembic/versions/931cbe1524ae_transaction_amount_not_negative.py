"""transaction amount not negative

Revision ID: 931cbe1524ae
Revises: 6fb1631eadba
Create Date: 2024-11-03 16:14:32.651853

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '931cbe1524ae'
down_revision: Union[str, None] = '6fb1631eadba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_created_id', sa.Integer(), nullable=True))

    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.execute("""
        UPDATE transactions
        SET user_created_id = user_from_id
        WHERE user_created_id IS NULL
        """)
        batch_op.alter_column("user_created_id", nullable=False)
        batch_op.create_foreign_key(batch_op.f('fk_transactions_user_created_id_users'), 'users', ['user_created_id'], ['id'])

        batch_op.execute("""
        UPDATE transactions
        SET user_from_id = user_to_id,
        user_to_id = user_from_id,
        converted_amount = -converted_amount,
        original_amount = -original_amount
        WHERE converted_amount < 0
        """)

        batch_op.create_check_constraint("converted_amount_ge_zero", "converted_amount >= 0")
        batch_op.create_check_constraint("original_amount_ge_zero", "original_amount >= 0 OR original_amount IS NULL")

    # don't loose triggers on sqlite:
    op.execute("""
    CREATE TRIGGER update_balance_update AFTER UPDATE ON transactions
    FOR EACH ROW
    BEGIN
        UPDATE users SET balance = balance + OLD.converted_amount WHERE id = OLD.user_from_id;
        UPDATE users SET balance = balance - OLD.converted_amount WHERE id = OLD.user_to_id;
        UPDATE users SET balance = balance - NEW.converted_amount WHERE id = NEW.user_from_id;
        UPDATE users SET balance = balance + NEW.converted_amount WHERE id = NEW.user_to_id;
    END;
    """)

    op.execute("""
    CREATE TRIGGER update_balance_insert AFTER INSERT ON transactions
    FOR EACH ROW
    BEGIN
        UPDATE users SET balance = balance - NEW.converted_amount WHERE id = NEW.user_from_id;
        UPDATE users SET balance = balance + NEW.converted_amount WHERE id = NEW.user_to_id;
    END;
    """)

    op.execute("""
    CREATE TRIGGER update_balance_delete AFTER DELETE ON transactions
    FOR EACH ROW
    BEGIN
        UPDATE users SET balance = balance + OLD.converted_amount WHERE id = OLD.user_from_id;
        UPDATE users SET balance = balance - OLD.converted_amount WHERE id = OLD.user_to_id;
    END;
    """)


def downgrade() -> None:
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_constraint("converted_amount_ge_zero", "check")
        batch_op.drop_constraint("original_amount_ge_zero", "check")
        batch_op.drop_constraint(batch_op.f('fk_transactions_user_created_id_users'), type_='foreignkey')
        batch_op.drop_column('user_created_id')

    # don't loose triggers on sqlite:
    op.execute("""
    CREATE TRIGGER update_balance_update AFTER UPDATE ON transactions
    FOR EACH ROW
    BEGIN
        UPDATE users SET balance = balance + OLD.converted_amount WHERE id = OLD.user_from_id;
        UPDATE users SET balance = balance - OLD.converted_amount WHERE id = OLD.user_to_id;
        UPDATE users SET balance = balance - NEW.converted_amount WHERE id = NEW.user_from_id;
        UPDATE users SET balance = balance + NEW.converted_amount WHERE id = NEW.user_to_id;
    END;
    """)

    op.execute("""
    CREATE TRIGGER update_balance_insert AFTER INSERT ON transactions
    FOR EACH ROW
    BEGIN
        UPDATE users SET balance = balance - NEW.converted_amount WHERE id = NEW.user_from_id;
        UPDATE users SET balance = balance + NEW.converted_amount WHERE id = NEW.user_to_id;
    END;
    """)

    op.execute("""
    CREATE TRIGGER update_balance_delete AFTER DELETE ON transactions
    FOR EACH ROW
    BEGIN
        UPDATE users SET balance = balance + OLD.converted_amount WHERE id = OLD.user_from_id;
        UPDATE users SET balance = balance - OLD.converted_amount WHERE id = OLD.user_to_id;
    END;
    """)
