"""Main mpay module.

This module defines the Mpay class which implements various operations
the user might want to do with the database in a UI-independent way.
"""

import datetime
import re
import logging
import dateutil.rrule
import sqlalchemy as sqa
import pandas as pd
from decimal import Decimal
from typing import Optional
from .config import Config
from . import db

_LOGGER = logging.getLogger(__name__)


def _print_tag_tree(tag: db.Tag, last: bool = True, header: str = "") -> str:
    elbow = "└──"
    pipe = "│  "
    tee = "├──"
    blank = "   "

    ret = (f"{header}{elbow if last else tee}"
           f"{tag.name}\t{tag.description if tag.description is not None else ''}"
           "\n")
    for i, c in enumerate(tag.children):
        ret += _print_tag_tree(c, header=header + (blank if last else pipe), last=i == len(tag.children) - 1)

    return ret


class MpayException(Exception):
    pass


class MpayValueError(ValueError, MpayException):
    pass


class Mpay:
    def __init__(self, config: Config, setup_database: bool = False):
        self.config = config
        self.db_engine = db.connect(config.db_url)
        if setup_database:
            db.setup_database(self.db_engine)
        elif not db.check_revision(self.db_engine):
            raise MpayException("Database revision does not match.")

    def __del__(self):
        self.db_engine.dispose()

    @staticmethod
    def ask_confirmation(question: str) -> bool:
        """Ask the user for confirmation.

        Overwrite this function if you want to implement it.
        Otherwise, it will assume the answer is yes.
        """
        return True

    def create_user(self, username: str) -> None:
        username = self.sanitize_user_name(username)
        with db.Session(self.db_engine) as session:
            u = db.User(name=username, balance=0)
            session.add(u)
            session.commit()

    def get_tag_tree_str(self) -> str:
        with db.Session(self.db_engine) as session:
            root_tags = session.query(db.Tag).filter_by(parent=None).all()
            ret = ""
            for i, t in enumerate(root_tags):
                ret += _print_tag_tree(t, i == len(root_tags)-1)
            return ret

    def _sql2df(self, statement, session) -> pd.DataFrame:
        # numpy_nullable can represent an int column with NULL values.
        # This is necessary to prevent converting id to float.
        return pd.read_sql(statement, session.bind,
                           dtype_backend='numpy_nullable')

    def get_tags_dataframe(self) -> pd.DataFrame:
        with db.Session(self.db_engine) as session:
            return self._sql2df(session.query(db.Tag).statement, session)

    def get_users_dataframe(self) -> pd.DataFrame:
        with db.Session(self.db_engine) as session:
            return self._sql2df(session.query(db.User).statement, session)

    def get_transactions_dataframe(self) -> pd.DataFrame:
        with db.Session(self.db_engine) as session:
            try:
                me = session.query(db.User).filter_by(name=self.config.user).one()
            except sqa.exc.NoResultFound:
                raise MpayException("current user does not exist in the database")

            return self._sql2df(
                db.history_select
                .where(
                    (db.Transaction.user_from_id == me.id) |
                    (db.Transaction.user_to_id == me.id)
                ),
                session
            )

    def get_orders_dataframe(self) -> pd.DataFrame:
        with db.Session(self.db_engine) as session:
            user_from = sqa.orm.aliased(db.User)
            user_to = sqa.orm.aliased(db.User)
            return self._sql2df(
                sqa.select(
                    db.StandingOrder.id,
                    db.StandingOrder.name,
                    user_from.name.label("user_from"),
                    user_to.name.label("user_to"),
                    db.StandingOrder.amount,
                    db.StandingOrder.note,
                    db.StandingOrder.rrule_str,
                    db.StandingOrder.dt_next_utc,
                    db.StandingOrder.dt_created_utc,
                )
                .join(user_from, db.StandingOrder.user_from)
                .join(user_to, db.StandingOrder.user_to),
                session
            )

    def sanitize_user_name(self, username: str) -> str:
        username = username.strip()
        if not re.match(r"^[a-z0-9_]+$", username):
            raise MpayValueError("username can only contain lowercase letters, numbers and underscore")
        return username

    def sanitize_tag_name(self, tag_name: str) -> str:
        tag_name = tag_name.strip()
        if not tag_name:
            raise MpayValueError("tag name must not be empty")
        if not re.match(r"^[a-zA-Z0-9_-]+$", tag_name):
            raise MpayValueError("tag name can only contain letters, numbers, dash and underscore")
        return tag_name

    def sanitize_order_name(self, order_name: str) -> str:
        order_name = order_name.strip()
        if not order_name:
            raise MpayValueError("order name must not be empty")
        if not re.match(r"^[a-zA-Z0-9_-]+$", order_name):
            raise MpayValueError("order name can only contain letters, numbers, dash and underscore")
        return order_name

    def sanitize_agent_name(self, agent_name: str) -> str:
        agent_name = agent_name.strip()
        if not agent_name:
            raise MpayValueError("agent name must not be empty")
        if not re.match(r"^[a-zA-Z0-9_-]+$", agent_name):
            raise MpayValueError("agent name can only contain letters, numbers, dash and underscore")
        return agent_name

    def find_tag(self, hierarchical_name: str, session) -> db.Tag:
        """Find a tag by its hierarchical_name."""
        path = hierarchical_name.strip().split("/")

        parent = None
        for t in path:
            current: db.Tag = session.query(db.Tag).filter_by(name=t, parent=parent).one()
            parent = current

        return current

    def create_hierarchical_tag(self, hierarchical_name: str, session) -> db.Tag:
        """Create a tag from a hierarchical_name.

        Creates parent tags as necessary. If the tag already exists, no error
        is raised and the existing tag is returned.

        Setting description is not supported, because this might create more
        than one tag.
        """
        path = hierarchical_name.strip().split("/")

        parent = None
        for t in path:
            current: Optional[db.Tag] = session.query(db.Tag).filter_by(name=t, parent=parent).one_or_none()
            if current is None:
                current = db.Tag(name=self.sanitize_tag_name(t), parent=parent)
                session.add(current)
            parent = current

        assert current is not None  # make mypy happy
        return current

    def create_tag(
            self,
            tag_name: str,
            description: Optional[str] = None,
            parent_hierarchical_name: Optional[str] = None
    ) -> None:
        tag_name = self.sanitize_tag_name(tag_name)
        with db.Session(self.db_engine) as session:
            parent = None
            if parent_hierarchical_name is not None:
                try:
                    parent = self.find_tag(parent_hierarchical_name, session)
                except sqa.exc.NoResultFound:
                    raise MpayException(f"parent tag '{parent_hierarchical_name}' does not exist")
            t = db.Tag(name=tag_name, description=description, parent=parent)
            session.add(t)
            session.commit()

    def create_agent(
            self,
            agent_name: str,
            description: Optional[str] = None
    ) -> None:
        agent_name = self.sanitize_agent_name(agent_name)
        with db.Session(self.db_engine) as session:
            a = db.Agent(name=agent_name, description=description)
            session.add(a)
            session.commit()

    def pay(
        self,
        recipient_name: str,
        converted_amount: Decimal,
        due: Optional[datetime.datetime] = None,
        original_currency: Optional[str] = None,
        original_amount: Optional[Decimal] = None,
        agent_name: Optional[str] = None,
        note: Optional[str] = None,
        tag_hierarchical_names: list[str] | tuple[str, ...] = [],
    ):
        recipient_name = self.sanitize_user_name(recipient_name)
        if due is None:
            due = datetime.datetime.now()

        with db.Session(self.db_engine) as session:
            try:
                sender = session.query(db.User).filter_by(name=self.config.user).one()
            except sqa.exc.NoResultFound:
                raise MpayException("current user does not exist in the database")

            try:
                recipient = session.query(db.User).filter_by(name=recipient_name).one()
            except sqa.exc.NoResultFound:
                raise MpayException("recipient user does not exist")

            # This is already checked by the db, but a python check will give
            # a more user-friendly error message.
            if sender == recipient:
                raise MpayException("recipient must not be the same as the current user")

            currency = None
            if original_currency is not None:
                try:
                    currency = session.query(db.Currency).filter_by(iso_4217=original_currency).one()
                except sqa.exc.NoResultFound:
                    raise MpayValueError("original_currency is not a known currency")

            agent = None
            if agent_name is not None:
                agent_name = self.sanitize_agent_name(agent_name)
                agent = session.query(db.Agent).filter_by(name=agent_name).one_or_none()
                if agent is None:
                    if not self.ask_confirmation(f"Agent {agent_name} does not exist. Create?"):
                        raise MpayException(f"agent {agent_name} does not exist")
                    agent = db.Agent(name=agent_name)

            # This should just work. If user enters "naive" timestamp on the
            # CLI, it will be interpreted as local time. If user enters
            # timestamp with timezone (e.g. Z at the end), it will be taken
            # into account.
            due_utc = due.astimezone(datetime.timezone.utc)

            tags = []
            for tag_hierarchical_name in tag_hierarchical_names:
                try:
                    tag = self.find_tag(tag_hierarchical_name, session)
                except sqa.exc.NoResultFound:
                    if not self.ask_confirmation(f"Tag {tag_hierarchical_name} does not exist. Create?"):
                        raise MpayException(f"tag {tag_hierarchical_name} does not exist")
                    tag = self.create_hierarchical_tag(tag_hierarchical_name, session)
                tags.append(tag)

            if converted_amount >= 0:
                s, r = sender, recipient
            else:
                s, r = recipient, sender

            t = db.Transaction(
                user_from=s,
                user_to=r,
                user_created=sender,
                converted_amount=abs(converted_amount),
                original_amount=abs(original_amount) if original_amount is not None else None,
                original_currency=currency,
                agent=agent,
                note=note,
                dt_due_utc=due_utc,
                tags=tags,
            )
            session.add(t)
            session.commit()

    def import_df(
        self,
        df: pd.DataFrame,
        user1_name: str,
        user2_name: str,
        agent_name: str
    ) -> None:
        """Import transactions from a dataframe.

        :param df: dataframe to import data from
        :param user1_name: name of user whose balance should be increased by
                           a transaction with positive amount
        :param user2_name: name of user whose balance should be decreased by
                           a transaction with positive amount
        :param agent_name: name of agent that should be attached to the
                           imported transactions

        df columns:
        amount: payment amount (int or float)
        dt_due: datetime
        note: str

        The whole operation is done in a single database transaction. This
        means that either everything is imported without error, or there is no
        change to the database at all.
        """

        agent_name = self.sanitize_agent_name(agent_name)
        user1_name = self.sanitize_user_name(user1_name)
        user2_name = self.sanitize_user_name(user2_name)

        with db.Session(self.db_engine) as session:
            agent = session.query(db.Agent).filter_by(name=agent_name).one_or_none()
            if agent is None:
                if not self.ask_confirmation(f"Agent {agent_name} does not exist. Create?"):
                    raise MpayException(f"agent {agent_name} does not exist")
                agent = db.Agent(name=agent_name)
                session.add(agent)

            try:
                user1 = session.query(db.User).filter_by(name=user1_name).one()
            except sqa.exc.NoResultFound:
                raise MpayException(f"user1 ({user1_name}) does not exist")
            try:
                user2 = session.query(db.User).filter_by(name=user2_name).one()
            except sqa.exc.NoResultFound:
                raise MpayException(f"user2 ({user2_name}) does not exist")

            user1_balance = Decimal("0")
            count = 0
            for _, row in df.iterrows():
                _LOGGER.debug("import row: %r", row)
                amount = Decimal(row.amount)
                if amount > 0:
                    user_from, user_to = user2, user1
                elif amount <= 0:
                    user_from, user_to = user1, user2

                note: Optional[str] = row.note
                # convert empty string to None
                if not note:
                    note = None

                dt_due_utc = datetime.datetime.fromisoformat(row.dt_due).astimezone(datetime.timezone.utc)

                user1_balance += amount
                count += 1

                t = db.Transaction(
                    user_from=user_from,
                    user_to=user_to,
                    user_created=user_from,
                    converted_amount=abs(amount),
                    agent=agent,
                    note=note,
                    dt_due_utc=dt_due_utc
                )

                session.add(t)

            if not self.ask_confirmation(f"{count} transactions imported, "
                                         f"final balance difference for user1: {user1_balance}. "
                                         "Proceed?"):
                raise Exception("cancelled by user")

            session.commit()

    def _execute_order(self, order: db.StandingOrder, session) -> None:
        dt_next_utc = order.dt_next_utc
        if dt_next_utc is None:
            # expired or disabled order
            return

        utc_now = datetime.datetime.now(datetime.timezone.utc)

        while (dt_next_utc is not None and
               dt_next_utc.replace(tzinfo=datetime.timezone.utc) <= utc_now
               ):
            # pay
            t = db.Transaction(
                user_from=order.user_from,
                user_to=order.user_to,
                user_created=order.user_from,
                converted_amount=order.amount,
                dt_due_utc=dt_next_utc,
                standing_order=order
            )
            session.add(t)

            # schedule next payment
            r = dateutil.rrule.rrulestr(order.rrule_str)
            prev_utc = dt_next_utc
            # we'll feed it naive utc datetime and get a naive utc result
            new_utc = r.after(dt_next_utc)
            assert new_utc is None or new_utc > prev_utc
            order.dt_next_utc = new_utc
            dt_next_utc = new_utc
            session.add(order)

        session.commit()

    def execute_orders(self) -> None:
        with db.Session(self.db_engine) as session:
            utc_now = datetime.datetime.now(datetime.timezone.utc)
            orders = session.query(db.StandingOrder).filter(db.StandingOrder.dt_next_utc < utc_now)
            for order in orders:
                self._execute_order(order, session)
            session.commit()

    def create_order(
        self,
        name: str,
        recipient_name: str,
        amount: Decimal,
        rrule: dateutil.rrule.rrule,
        note: Optional[str] = None,
    ) -> None:
        """Create a standing order.

        :param rrule: Recurrence rule. dtstart will be regarded as UTC.
        """
        name = self.sanitize_order_name(name)
        recipient_name = self.sanitize_user_name(recipient_name)

        if amount <= 0:
            raise MpayValueError("amount must be greater than zero")

        with db.Session(self.db_engine) as session:
            try:
                sender = session.query(db.User).filter_by(name=self.config.user).one()
            except sqa.exc.NoResultFound:
                raise MpayException("current user does not exist in the database")

            try:
                recipient = session.query(db.User).filter_by(name=recipient_name).one()
            except sqa.exc.NoResultFound:
                raise MpayException("recipient user does not exist")

            o = db.StandingOrder(
                name=name,
                rrule_str=str(rrule),
                user_from=sender,
                user_to=recipient,
                amount=amount,
                note=note,
                dt_next_utc=rrule[0]
            )
            session.add(o)
            session.commit()

    def disable_order(self, order_name: str) -> bool:
        """Disable a standing order. This operation is irreversible.

        :return: True on success, False otherwise
        """
        order_name = self.sanitize_order_name(order_name)

        with db.Session(self.db_engine) as session:
            try:
                user = session.query(db.User).filter_by(name=self.config.user).one()
            except sqa.exc.NoResultFound:
                raise MpayException("current user does not exist in the database")

            try:
                order = session.query(db.StandingOrder).filter_by(name=order_name, user_from=user).one()
            except sqa.exc.NoResultFound:
                raise MpayException(f"standing order {order_name} with user_from={user.name} does not exist")

            if order.dt_next_utc is None:
                # already disabled
                return True

            if not self.ask_confirmation("This operation is irreversible. Proceed?"):
                return False

            order.dt_next_utc = None
            session.add(order)
            session.commit()
        return True

    def check(self) -> None:
        """Execute integrity checks on the database.

        Most things are checked by the database engine itself, but there's
        still a few checks that need to be done manually.

        This function returns nothing. If an error is encountered,
        AssertionError is raised.
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
