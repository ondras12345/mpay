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


class Mpay:
    def __init__(self, config: Config):
        self.config = config
        self.db_engine = db.connect(config.db_url)

    def create_database(self):
        db.create_tables(self.db_engine)

    @staticmethod
    def ask_confirmation(question: str) -> bool:
        """Ask the user for confirmation.

        Overwrite this function if you want to implement it.
        Otherwise, it will assume the answer is yes.
        """
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

    def get_tag_tree_str(self) -> str:
        with db.Session(self.db_engine) as session:
            root_tags = session.query(db.Tag).filter_by(parent=None).all()
            ret = ""
            for i, t in enumerate(root_tags):
                ret += _print_tag_tree(t, i == len(root_tags)-1)
            return ret

    def _sql2df(self, statement, session):
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
            user_from = sqa.orm.aliased(db.User)
            user_to = sqa.orm.aliased(db.User)
            return self._sql2df(
                sqa.select(
                    db.Transaction.id,
                    user_from.name.label("user_from"),
                    user_to.name.label("user_to"),
                    db.Transaction.converted_amount,
                    db.Currency.iso_4217.label("original_currency"),
                    db.Transaction.original_amount,
                    db.Agent.name.label("agent"),
                    # Standing order name is not unique! (user_from, name) is,
                    # but that's too many columns.
                    db.Transaction.standing_order_id,
                    db.Transaction.note,
                    db.Transaction.dt_due_utc,
                    db.Transaction.dt_created_utc,
                )
                .join(user_from, db.Transaction.user_from)
                .join(user_to, db.Transaction.user_to)
                .outerjoin(db.Transaction.original_currency)
                .outerjoin(db.Transaction.agent)
                .order_by(db.Transaction.dt_due_utc),
                session
            )

    def _sanitize_tag_name(self, tag_name: str) -> str:
        tag_name = tag_name.strip()
        if not tag_name:
            raise ValueError("tag name must not be empty")
        if not re.match(r"^[a-zA-Z0-9_-]+$", tag_name):
            raise ValueError("tag name can only contain letters, numbers, dash and underscore")
        return tag_name

    def _sanitize_order_name(self, order_name: str) -> str:
        order_name = order_name.strip()
        if not order_name:
            raise ValueError("order name must not be empty")
        if not re.match(r"^[a-zA-Z0-9_-]+$", order_name):
            raise ValueError("order name can only contain letters, numbers, dash and underscore")
        return order_name

    def create_tag(
            self,
            tag_name: str,
            description: Optional[str] = None,
            parent_name: Optional[str] = None
    ) -> None:
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

    def _execute_transaction(self, t: db.Transaction):
        """Update users' balance based on specified transaction.

        IMPORTANT: This will only work once per transaction. SqlAlchemy seems
        to only execute the last UPDATE statement if called multiple times.
        Call session.commit() after executing each transaction.
        """
        _LOGGER.debug("_execute_transaction %r", t)
        # cannot use +=, we need the addition to be done by the database
        t.user_from.balance = db.User.balance - t.converted_amount
        t.user_to.balance = db.User.balance + t.converted_amount

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
            self._execute_transaction(t)
            session.commit()

    def _execute_order(self, order: db.StandingOrder, session) -> None:
        if order.dt_next_utc is None:
            # expired or disabled order
            return

        utc_now = datetime.datetime.now(datetime.timezone.utc)

        while order.dt_next_utc.replace(tzinfo=datetime.timezone.utc) <= utc_now:
            # pay
            t = db.Transaction(
                user_from=order.user_from,
                user_to=order.user_to,
                converted_amount=order.amount,
                dt_due_utc=order.dt_next_utc,
                standing_order=order
            )
            session.add(t)
            self._execute_transaction(t)

            # schedule next payment
            r = dateutil.rrule.rrulestr(order.rrule_str)
            prev_utc = order.dt_next_utc
            # we'll feed it naive utc datetime and get a naive utc result
            order.dt_next_utc = r.after(order.dt_next_utc)
            assert order.dt_next_utc > prev_utc
            session.add(order)

            # Important! We need to commit after each call to
            # _execute_transaction.
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

        if amount <= 0:
            raise ValueError("amount must be greater than zero")

        with db.Session(self.db_engine) as session:
            try:
                sender = session.query(db.User).filter_by(name=self.config.user).one()
            except sqa.exc.NoResultFound:
                raise ValueError("current user does not exist in the database")

            try:
                recipient = session.query(db.User).filter_by(name=recipient_name).one()
            except sqa.exc.NoResultFound:
                raise ValueError("recipient user does not exist")

            o = db.StandingOrder(
                name=self._sanitize_order_name(name),
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
        with db.Session(self.db_engine) as session:
            try:
                user = session.query(db.User).filter_by(name=self.config.user).one()
            except sqa.exc.NoResultFound:
                raise ValueError("current user does not exist in the database")

            try:
                order = session.query(db.StandingOrder).filter_by(name=order_name, user_from=user).one()
            except sqa.exc.NoResultFound:
                raise ValueError(f"standing order {order_name} with user_from={user.name} does not exist")

            if order.dt_next_utc is None:
                # already disabled
                return True

            if not self.ask_confirmation("This operation is irreversible. Proceed?"):
                return False

            order.dt_next_utc = None
            session.add(order)
            session.commit()
        return True

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
