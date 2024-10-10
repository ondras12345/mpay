import sqlalchemy as sqa
import mpay.db as db
import re


def create_user(db_engine: sqa.engine, username: str) -> None:
    username = username.strip()
    if not re.match(r"^[a-z0-9_]+$", username):
        raise ValueError("username can only contain lowercase letters, numbers and underscore")
    with db.Session(db_engine) as session:
        u = db.User(name=username, balance=0)
        session.add(u)
        session.commit()

def list_users(db_engine: sqa.engine) -> list[db.User]:
    with Session(db_engine) as session:
        users = session.query(db.User)
        return list(users)
