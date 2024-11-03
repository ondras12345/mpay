"""SQL database schema definition."""

import datetime
import logging
import sqlalchemy as sqa
from sqlalchemy import (
    create_engine, ForeignKey, PrimaryKeyConstraint, CheckConstraint,
    UniqueConstraint, String, Table, Column, Integer, DDL, insert,
    MetaData
)

from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship
)

from sqlalchemy.orm import Session  # noqa: F401
from sqlalchemy import func  # noqa: F401

from sqlalchemy.types import Numeric

from typing import Optional
from decimal import Decimal
import alembic
import alembic.config
import pathlib


_LOGGER = logging.getLogger(__name__)


class Base(DeclarativeBase):
    # constraint naming (needed by alembic):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s"
    })

    # extra mysql args: don't forget to include in __table_args__ in derived
    # classes
    _mysql_args = {
        "mysql_default_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_520_ci",
    }

    __table_args__: tuple | dict = _mysql_args


money_type = Numeric(precision=9, scale=3, asdecimal=True)


def aware_utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)
    balance: Mapped[Decimal] = mapped_column(money_type)

    # TODO expire User.balance after transaction trigger changes their balance
    # - there seems to be no easy way to do that from here. It would be
    # possible by adding an event for session.flush.

    # This could use a deferred constraint checking that SUM(balance) = 0,
    # but I don't think MySQL supports that.


class Currency(Base):
    __tablename__ = "currencies"
    id: Mapped[int] = mapped_column(primary_key=True)
    iso_4217: Mapped[str] = mapped_column(String(3), unique=True)
    name: Mapped[Optional[str]] = mapped_column(String(32))


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32))
    description: Mapped[Optional[str]] = mapped_column(String(255))
    transactions: Mapped[list["Transaction"]] = relationship(secondary="transactions_tags", back_populates="tags")
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey(__tablename__ + ".id"))
    parent: Mapped[Optional["Tag"]] = relationship(back_populates="children", remote_side=[id])
    children: Mapped[list["Tag"]] = relationship(back_populates="parent")
    __table_args__ = (
        UniqueConstraint("name", "parent_id"),
        # MySQL does not like CHECK on AUTO_INCREMENT column, hence the ddl_if
        CheckConstraint("parent_id <> id", "parent_not_self").ddl_if(dialect="sqlite"),
        Base._mysql_args
    )

    @property
    def hierarchical_name(self):
        if self.parent is None:
            return self.name
        return self.parent.hierarchical_name + "/" + self.name


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(255))


class StandingOrder(Base):
    __tablename__ = "standing_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32))
    user_from_id: Mapped[int] = mapped_column(ForeignKey(User.__tablename__ + ".id"))
    user_from: Mapped[User] = relationship(foreign_keys=[user_from_id])
    user_to_id: Mapped[int] = mapped_column(ForeignKey(User.__tablename__ + ".id"))
    user_to: Mapped[User] = relationship(foreign_keys=[user_to_id])
    amount: Mapped[Decimal] = mapped_column(money_type)
    note: Mapped[Optional[str]] = mapped_column(String(255))
    # rrule dtstart is stored as a naive UTC datetime
    rrule_str: Mapped[str] = mapped_column(String(255))
    # UTC date when next transaction should occur or None for disabled /
    # expired order. Cannot be recovered once set to None.
    dt_next_utc: Mapped[Optional[datetime.datetime]]
    dt_created_utc: Mapped[datetime.datetime] = mapped_column(default=aware_utcnow)
    __table_args__ = (
        UniqueConstraint("name", "user_from_id"),
        CheckConstraint("user_from_id <> user_to_id", "user_from_to_different"),
        # alembic does not seem to support check constraint in column definition
        CheckConstraint("amount >= 0", "amount_ge_zero"),
        Base._mysql_args
    )


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_from_id: Mapped[int] = mapped_column(ForeignKey(User.__tablename__ + ".id"))
    user_from: Mapped[User] = relationship(foreign_keys=[user_from_id])
    user_to_id: Mapped[int] = mapped_column(ForeignKey(User.__tablename__ + ".id"))
    user_to: Mapped[User] = relationship(foreign_keys=[user_to_id])
    original_amount: Mapped[Optional[Decimal]] = mapped_column(money_type)
    original_currency_id: Mapped[Optional[int]] = mapped_column(ForeignKey(Currency.__tablename__ + ".id"))
    original_currency: Mapped[Optional[Currency]] = relationship()
    # converted_amount is amount in system base currency
    converted_amount: Mapped[Decimal] = mapped_column(money_type)
    standing_order_id: Mapped[Optional[int]] = mapped_column(ForeignKey(StandingOrder.__tablename__ + ".id"))
    standing_order: Mapped[Optional[StandingOrder]] = relationship()
    agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey(Agent.__tablename__ + ".id"))
    agent: Mapped[Optional[Agent]] = relationship()
    note: Mapped[Optional[str]] = mapped_column(String(255))
    dt_created_utc: Mapped[datetime.datetime] = mapped_column(default=aware_utcnow)
    dt_due_utc: Mapped[datetime.datetime]
    tags: Mapped[list[Tag]] = relationship(secondary="transactions_tags", back_populates="transactions")
    __table_args__ = (
        # either both null or both not null
        CheckConstraint(
            "(original_currency_id IS NULL) = (original_amount IS NULL)",
            "both_original_amount_and_currency"
        ),
        CheckConstraint("user_from_id <> user_to_id", "user_from_to_different"),
        # Currently, we don't support adding transactions with future due
        # date.
        CheckConstraint("dt_due_utc <= dt_created_utc", "dt_due_not_in_future"),
        Base._mysql_args
    )


sqa.event.listen(
    Transaction.__table__, "after_create",
    DDL(f"""
    CREATE TRIGGER update_balance_update AFTER UPDATE ON {Transaction.__tablename__}
    FOR EACH ROW
    BEGIN
        UPDATE {User.__tablename__} SET balance = balance + OLD.converted_amount WHERE id = OLD.user_from_id;
        UPDATE {User.__tablename__} SET balance = balance - OLD.converted_amount WHERE id = OLD.user_to_id;
        UPDATE {User.__tablename__} SET balance = balance - NEW.converted_amount WHERE id = NEW.user_from_id;
        UPDATE {User.__tablename__} SET balance = balance + NEW.converted_amount WHERE id = NEW.user_to_id;
    END;
    """)
)

sqa.event.listen(
    Transaction.__table__, "after_create",
    DDL(f"""
    CREATE TRIGGER update_balance_insert AFTER INSERT ON {Transaction.__tablename__}
    FOR EACH ROW
    BEGIN
        UPDATE {User.__tablename__} SET balance = balance - NEW.converted_amount WHERE id = NEW.user_from_id;
        UPDATE {User.__tablename__} SET balance = balance + NEW.converted_amount WHERE id = NEW.user_to_id;
    END;
    """)
)

sqa.event.listen(
    Transaction.__table__, "after_create",
    DDL(f"""
    CREATE TRIGGER update_balance_delete AFTER DELETE ON {Transaction.__tablename__}
    FOR EACH ROW
    BEGIN
        UPDATE {User.__tablename__} SET balance = balance + OLD.converted_amount WHERE id = OLD.user_from_id;
        UPDATE {User.__tablename__} SET balance = balance - OLD.converted_amount WHERE id = OLD.user_to_id;
    END;
    """)
)


transactions_tags = Table(
    "transactions_tags",
    Base.metadata,
    Column("transaction_id", Integer,
           ForeignKey(Transaction.__tablename__ + ".id", ondelete="CASCADE")),
    Column("tag_id", Integer,
           ForeignKey(Tag.__tablename__ + ".id", ondelete="CASCADE")),
    PrimaryKeyConstraint("transaction_id", "tag_id"),
)


def alembic_config(db_engine) -> alembic.config.Config:
    alembic_cfg_file = pathlib.Path(__file__).parents[0] / "alembic.ini"
    _LOGGER.debug("alembic config file: %s", alembic_cfg_file)
    if not alembic_cfg_file.exists():
        raise Exception(f"Alembic config file does not exist: {alembic_cfg_file}")
    alembic_cfg = alembic.config.Config(alembic_cfg_file)
    alembic_cfg.set_main_option("sqlalchemy.url", "")
    alembic_cfg.attributes["engine"] = db_engine
    return alembic_cfg


def connect(db_url: str) -> sqa.engine.Engine:
    engine = create_engine(db_url)

    dialect_name = engine.dialect.name
    _LOGGER.info("db engine dialect name: %s", dialect_name)
    if "sqlite" in dialect_name.lower():
        def set_sqlite_pragma(dbapi_connection, connection_record):
            _LOGGER.info("setting sqlite pragmas")
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        sqa.event.listen(engine, "connect", set_sqlite_pragma)

    return engine


def check_revision(db_engine) -> bool:
    """Check whether the connected database has a compatible schema."""
    with db_engine.connect() as conn:
        context = alembic.runtime.migration.MigrationContext.configure(conn)
        current_rev = context.get_current_revision()
    _LOGGER.debug("Database schema revision: %s", current_rev)

    alembic_cfg = alembic_config(db_engine)
    head = alembic.script.ScriptDirectory.from_config(alembic_cfg).get_current_head()
    _LOGGER.debug("Alembic head: %s", head)
    return current_rev == head


def setup_database(db_engine) -> None:
    """Create database or upgrade database schema."""
    # We could theoretically speed up the process of creating a database
    # from scratch by calling
    # Base.metadata.create_all(db_engine)
    # And then tagging the current state as 'head'.
    # However, that might result in inconsistencies compared to databases
    # created with alembic. It does not seem necessary to implement this at
    # this time.

    alembic_cfg = alembic_config(db_engine)
    alembic.command.upgrade(alembic_cfg, "head")

    # Populate currencies table with most commonly used values.
    with Session(db_engine) as session:
        CURRENCIES = {
            "USD": "United States dollar",
            "EUR": "Euro",
        }
        session.execute(
            insert(Currency)
            .prefix_with("OR IGNORE", dialect="sqlite")
            .prefix_with("IGNORE", dialect="mysql"),
            [
                {"iso_4217": iso_4217, "name": name}
                for iso_4217, name in CURRENCIES.items()
            ],
        )
        session.commit()
