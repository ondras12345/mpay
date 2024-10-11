import sqlalchemy as sqa
from sqlalchemy import (
    create_engine, ForeignKey, PrimaryKeyConstraint, CheckConstraint
)

from sqlalchemy.orm import (
    declarative_base, Mapped, mapped_column, relationship
)

from sqlalchemy.orm import Session  # noqa: F401

from sqlalchemy.types import Numeric

from typing import Optional
from enum import Enum
from decimal import Decimal
import datetime


class StandingOrderPeriod(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    # TODO


Base = declarative_base()

money_type = Numeric(precision=9, scale=3, asdecimal=True)


def aware_utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    balance: Mapped[Decimal] = mapped_column(money_type)


class Currency(Base):
    __tablename__ = "currencies"
    id: Mapped[int] = mapped_column(primary_key=True)
    iso_4217: Mapped[str] = mapped_column(unique=True)
    name: Mapped[Optional[str]]


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[Optional[str]]
    transactions: Mapped[list["Transaction"]] = relationship(secondary="transactions_tags", back_populates="tags")
    # tags can be a tree
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey(__tablename__ + ".id"))
    parent: Mapped[Optional["Tag"]] = relationship()
    __table_args__ = (
        CheckConstraint("parent_id <> id"),
    )


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[Optional[str]]


class StandingOrder(Base):
    __tablename__ = "standing_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool]
    period: Mapped[StandingOrderPeriod]  # TODO Enum se uklada jako string, zkusit v MySQL
    repeat_count: Mapped[Optional[int]]
    user_from_id: Mapped[int] = mapped_column(ForeignKey(User.__tablename__ + ".id"))
    user_from: Mapped[User] = relationship(foreign_keys=[user_from_id])
    user_to_id: Mapped[int] = mapped_column(ForeignKey(User.__tablename__ + ".id"))
    user_to: Mapped[User] = relationship(foreign_keys=[user_to_id])
    amount: Mapped[Decimal] = mapped_column(money_type)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_from_id: Mapped[int] = mapped_column(ForeignKey(User.__tablename__ + ".id"))
    user_from: Mapped[User] = relationship(foreign_keys=[user_from_id])
    user_to_id: Mapped[int] = mapped_column(ForeignKey(User.__tablename__ + ".id"))
    user_to: Mapped[User] = relationship(foreign_keys=[user_to_id])
    original_amount: Mapped[Optional[Decimal]] = mapped_column(money_type)
    currency_id: Mapped[int] = mapped_column(ForeignKey(Currency.__tablename__ + ".id"))
    currency: Mapped[Currency] = relationship()
    # converted_amount is amount in system base currency
    converted_amount: Mapped[Decimal] = mapped_column(money_type)
    standing_order_id: Mapped[Optional[int]] = mapped_column(ForeignKey(StandingOrder.__tablename__ + ".id"))
    standing_order: Mapped[Optional[StandingOrder]] = relationship()
    agent_id: Mapped[int] = mapped_column(ForeignKey(Agent.__tablename__ + ".id"))
    agent: Mapped[Optional[Agent]] = relationship()
    note: Mapped[Optional[str]]
    dt_created_utc: Mapped[datetime.datetime] = mapped_column(default=aware_utcnow)
    dt_due_utc: Mapped[datetime.datetime]
    tags: Mapped[list[Tag]] = relationship(secondary="transactions_tags", back_populates="transactions")


class TransactionTag(Base):
    __tablename__ = "transactions_tags"
    __table_args__ = (
        PrimaryKeyConstraint("transaction_id", "tag_id"),
    )
    transaction_id: Mapped[int] = mapped_column(ForeignKey(Transaction.__tablename__ + ".id"))
    tag_id: Mapped[int] = mapped_column(ForeignKey(Tag.__tablename__ + ".id"))


def connect(db_url: str) -> sqa.engine:
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    return engine
