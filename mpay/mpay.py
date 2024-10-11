import datetime
import re
import sqlalchemy as sqa
import pandas as pd
from decimal import Decimal
from typing import Optional
from .config import Config
from . import db


class Mpay:
    def __init__(self, config: Config):
        self.config = config
        self.db_engine = db.connect(config.db_url)

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

    def create_tag(self, tag_name: str, description: Optional[str] = None, parent_name: Optional[str] = None) -> None:
        tag_name = tag_name.strip()
        if not re.match(r"^[a-zA-Z0-9_-]+$", tag_name):
            raise ValueError("tag name can only contain letters, numbers, dash and underscore")
        with db.Session(self.db_engine) as session:
            parent = None
            if parent_name is not None:
                try:
                    parent = session.query(db.Tag).filter_by(name=parent_name).one()
                except sqa.exc.NoResultFound:
                    raise KeyError(f"parent tag '{parent_name}' does not exist")
            t = db.Tag(name=tag_name, description=description, parent=parent)
            session.add(t)
            session.commit()

    def pay(
        self,
        recipient: str,
        converted_amount: Decimal,
        original_currency: str,
        original_amount: Decimal,
        due: datetime.datetime,
        agent: str | None = None,
        note: str | None = None,
        tags: list[str] = [],
    ):
        # TODO
        # TODO due utc
        pass
