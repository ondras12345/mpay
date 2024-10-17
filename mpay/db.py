import datetime
import logging
import sqlalchemy as sqa
from sqlalchemy import (
    create_engine, ForeignKey, PrimaryKeyConstraint, CheckConstraint,
    UniqueConstraint, String
)

from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship
)

from sqlalchemy.orm import Session  # noqa: F401
from sqlalchemy import func  # noqa: F401

from sqlalchemy.types import Numeric

from typing import Optional
from decimal import Decimal


_LOGGER = logging.getLogger(__name__)


class Base(DeclarativeBase):
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
    name: Mapped[str] = mapped_column(String(32), unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    transactions: Mapped[list["Transaction"]] = relationship(secondary="transactions_tags", back_populates="tags")
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey(__tablename__ + ".id"))
    parent: Mapped[Optional["Tag"]] = relationship(back_populates="children", remote_side=[id])
    children: Mapped[list["Tag"]] = relationship(back_populates="parent")
    # TODO MySQL does not like CHECK on AUTO_INCREMENT column
    # __table_args__ = (
    #     CheckConstraint("parent_id <> id", "parent_not_self"),
    #     Base._mysql_args
    # )


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
        CheckConstraint("amount > 0"),
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
        CheckConstraint("(original_currency_id IS NULL) = (original_amount IS NULL)"),
        CheckConstraint("user_from_id <> user_to_id"),
        # Currently, we don't support adding transactions with future due
        # date.
        CheckConstraint("dt_due_utc < dt_created_utc"),
        Base._mysql_args
    )


class TransactionTag(Base):
    __tablename__ = "transactions_tags"
    __table_args__ = (
        PrimaryKeyConstraint("transaction_id", "tag_id"),
        Base._mysql_args
    )
    transaction_id: Mapped[int] = mapped_column(ForeignKey(Transaction.__tablename__ + ".id"))
    tag_id: Mapped[int] = mapped_column(ForeignKey(Tag.__tablename__ + ".id"))


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


def create_tables(db_engine) -> None:
    Base.metadata.create_all(db_engine)
