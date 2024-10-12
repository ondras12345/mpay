import datetime
import re
import logging
import sqlalchemy as sqa
import pandas as pd
from decimal import Decimal
from typing import Optional
from .config import Config
from . import db

_LOGGER = logging.getLogger(__name__)


class Mpay:
    def __init__(self, config: Config):
        self.config = config
        self.db_engine = db.connect(config.db_url)

    @staticmethod
    def ask_confirmation(question: str) -> bool:
        """Ask the user for confirmation. Overwrite this function if you want to use it."""
        return True

    def create_user(self, username: str) -> None:
        username = username.strip()
        if not re.match(r"^[a-z0-9_]+$", username):
            raise ValueError("username can only contain lowercase letters, numbers and underscore")
        with db.Session(self.db_engine) as session:
            u = db.User(name=username, balance=0)
            session.add(u)
            session.commit()

    def get_users(self) -> list[db.User]:
        with db.Session(self.db_engine) as session:
            users = session.query(db.User)
            return list(users)

    def get_tags(self) -> list[db.Tag]:
        with db.Session(self.db_engine) as session:
            tags = session.query(db.Tag)
            return list(tags)

    def get_tags_dataframe(self) -> pd.DataFrame:
        with db.Session(self.db_engine) as session:
            return pd.read_sql(session.query(db.Tag).statement, session.bind)

    def get_users_dataframe(self) -> pd.DataFrame:
        with db.Session(self.db_engine) as session:
            return pd.read_sql(session.query(db.User).statement, session.bind)

    def _sanitize_tag_name(self, tag_name: str) -> str:
        tag_name = tag_name.strip()
        if not tag_name:
            raise ValueError("tag name must not be empty")
        if not re.match(r"^[a-zA-Z0-9_-]+$", tag_name):
            raise ValueError("tag name can only contain letters, numbers, dash and underscore")
        return tag_name

    def create_tag(self, tag_name: str, description: Optional[str] = None, parent_name: Optional[str] = None) -> None:
        tag_name = self._sanitize_tag_name(tag_name)
        with db.Session(self.db_engine) as session:
            parent = None
            if parent_name is not None:
                try:
                    parent = session.query(db.Tag).filter_by(name=parent_name).one()
                except sqa.exc.NoResultFound:
                    raise ValueError(f"parent tag '{parent_name}' does not exist")
            t = db.Tag(name=tag_name, description=description, parent=parent)
            session.add(t)
            session.commit()

    def pay(
        self,
        recipient_name: str,
        converted_amount: Decimal,
        due: datetime.datetime,
        original_currency: Optional[str] = None,
        original_amount: Optional[Decimal] = None,
        agent_name: Optional[str] = None,
        note: Optional[str] = None,
        tag_names: list[str] = [],
    ):
        with db.Session(self.db_engine) as session:
            try:
                sender = session.query(db.User).filter_by(name=self.config.user).one()
            except sqa.exc.NoResultFound:
                raise ValueError("current user does not exist in the database")

            try:
                recipient = session.query(db.User).filter_by(name=recipient_name).one()
            except sqa.exc.NoResultFound:
                raise ValueError("recipient user does not exist")

            # This is already checked by the db, but a python check will give
            # a more user-friendly error message.
            if sender == recipient:
                raise ValueError("recipient must not be the same as the current user")

            currency = None
            if original_currency is not None:
                try:
                    currency = session.query(db.Currency).filter_by(iso_4217=original_currency).one()
                except sqa.exc.NoResultFound:
                    raise ValueError("original_currency is not a known currency")

            agent = None
            if agent_name is not None:
                agent = session.query(db.Agent).filter_by(name=agent_name).one_or_none()
                if agent is None:
                    if not self.ask_confirmation(f"Agent {agent_name} does not exist. Create?"):
                        raise ValueError(f"agent {agent_name} does not exist")
                    agent = db.Agent(name=agent_name)

            # This should just work. If user enters "naive" timestamp on the
            # CLI, it will be interpreted as local time. If user enters
            # timestamp with timezone (e.g. Z at the end), it will be taken
            # into account.
            due_utc = due.astimezone(datetime.timezone.utc)

            tags = []
            for tag_name in tag_names:
                tag_name = self._sanitize_tag_name(tag_name)
                try:
                    tag = session.query(db.Tag).filter_by(name=tag_name).one()
                except sqa.exc.NoResultFound:
                    if not self.ask_confirmation(f"Tag {tag_name} does not exist. Create?"):
                        raise ValueError(f"tag {tag_name} does not exist")
                    tag = db.Tag(name=tag_name)
                tags.append(tag)

            t = db.Transaction(
                user_from=sender,
                user_to=recipient,
                converted_amount=converted_amount,
                original_amount=original_amount,
                original_currency=currency,
                agent=agent,
                note=note,
                dt_due_utc=due_utc,
                tags=tags,
            )
            session.add(t)

            # cannot use +=, we need the addition to be done by the database
            sender.balance = db.User.balance - converted_amount
            recipient.balance = db.User.balance + converted_amount

            session.commit()

    def check(self):
        """Execute integrity checks on the database.

        Most things are checked by the database engine itself, but there's
        still a few checks that need to be done manually.
        """
        _LOGGER.info("executing database checks")
        with db.Session(self.db_engine) as session:
            dialect_name = self.db_engine.dialect.name
            if "sqlite" in dialect_name.lower():
                _LOGGER.warning("db engine is sqlite, running sqlite-specific checks")
                integrity_result = session.execute(sqa.sql.text("PRAGMA integrity_check")).one()
                if integrity_result[0].lower().strip() != "ok":
                    raise AssertionError("sqlite PRAGMA integrity_check reported errors")
                foreign_key_result = session.execute(sqa.sql.text("PRAGMA foreign_key_check")).all()
                if len(foreign_key_result) != 0:
                    raise AssertionError("sqlite foreign_key_check reported errors")

            balance_sum = session.query(db.func.sum(db.User.balance)).scalar()
            _LOGGER.info("balance sum: %s", balance_sum)
            # balance_sum could be None if there are no users in the table
            if balance_sum != 0 and balance_sum is not None:
                raise AssertionError("balance sum is non-zero")

            # TODO lock tables users, transactions - this seems to be MySQL
            # specific

            users = session.query(db.User).all()
            for user in users:
                outgoing_sum = (
                    session.query(db.func.sum(db.Transaction.converted_amount))
                    .filter_by(user_from=user)
                    .scalar()
                )
                incoming_sum = (
                    session.query(db.func.sum(db.Transaction.converted_amount))
                    .filter_by(user_to=user)
                    .scalar()
                )
                _LOGGER.info("user=%s, outgoing_sum=%s, incoming_sum=%s, balance=%s",
                             user.name, outgoing_sum, incoming_sum, user.balance)

                if outgoing_sum is None:
                    outgoing_sum = 0
                if incoming_sum is None:
                    incoming_sum = 0

                if incoming_sum - outgoing_sum != user.balance:
                    raise AssertionError(f"balance does not match transaction sum for user {user.name}")
