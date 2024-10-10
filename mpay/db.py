import sqlalchemy as sqa
from sqlalchemy import (
    create_engine, ForeignKey, PrimaryKeyConstraint, DateTime
)

from sqlalchemy.orm import (
    declarative_base, Mapped, mapped_column, relationship,
    Session
)

from typing import Optional
from enum import Enum
import datetime


class StandingOrderPeriod(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    # TODO


Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    balance: Mapped[float]  # TODO float neni dobry pro menu


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


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[Optional[str]]


class StandingOrder(Base):
    __tablename__ = "standing_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool]
    period: Mapped[StandingOrderPeriod]  # TODO Enum se uklada jako string
    repeat_count: Mapped[Optional[int]]
    user_from_id: Mapped[int] = mapped_column(ForeignKey(User.__tablename__ + ".id"))
    user_from: Mapped[User] = relationship(foreign_keys=[user_from_id])
    user_to_id: Mapped[int] = mapped_column(ForeignKey(User.__tablename__ + ".id"))
    user_to: Mapped[User] = relationship(foreign_keys=[user_to_id])
    amount: Mapped[float]  # TODO currency type


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_from_id: Mapped[int] = mapped_column(ForeignKey(User.__tablename__ + ".id"))
    user_from: Mapped[User] = relationship(foreign_keys=[user_from_id])
    user_to_id: Mapped[int] = mapped_column(ForeignKey(User.__tablename__ + ".id"))
    user_to: Mapped[User] = relationship(foreign_keys=[user_to_id])
    original_amount: Mapped[Optional[float]]
    currency_id: Mapped[int] = mapped_column(ForeignKey(Currency.__tablename__ + ".id"))
    currency: Mapped[Currency] = relationship()
    # converted_amount is amount in system base currency
    converted_amount: Mapped[float]
    standing_order_id: Mapped[Optional[int]] = mapped_column(ForeignKey(StandingOrder.__tablename__ + ".id"))
    standing_order: Mapped[Optional[StandingOrder]] = relationship()
    agent_id: Mapped[int] = mapped_column(ForeignKey(Agent.__tablename__ + ".id"))
    agent: Mapped[Optional[Agent]] = relationship()
    note: Mapped[Optional[str]]
    # TODO utc dateime
    dt_created: Mapped[datetime.datetime]
    dt_due: Mapped[datetime.datetime]
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
