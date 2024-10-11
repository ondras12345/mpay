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
