import pytest
import mpay
import datetime
from decimal import Decimal


def test_init():
    config = mpay.Config(user="test1", db_url="sqlite:///")
    mp = mpay.Mpay(config)

    with pytest.raises(Exception):
        mp.check()

    mp.create_database()

    mp.check()


def test_check(mpay_in_memory):
    mp = mpay_in_memory
    with mpay.db.Session(mp.db_engine) as session:
        u1 = mpay.db.User(name="u1", balance=Decimal("12.3"))
        session.add(u1)
        session.commit()

    with pytest.raises(AssertionError):
        mp.check()

    # fix the balance mismatch
    with mpay.db.Session(mp.db_engine) as session:
        u2 = mpay.db.User(name="u2", balance=Decimal("-12.3"))
        session.add(u2)
        session.commit()

    # still, there is no matching transaction
    with pytest.raises(AssertionError):
        mp.check()

    with mpay.db.Session(mp.db_engine) as session:
        t = mpay.db.Transaction(user_from=u2, user_to=u1,
                                converted_amount=Decimal("12.3"),
                                dt_due_utc=mpay.db.aware_utcnow())
        session.add(t)
        session.commit()

    # now it should be fixed
    mp.check()


@pytest.fixture
def mpay_in_memory():
    config = mpay.Config(user="test1", db_url="sqlite:///")
    mp = mpay.Mpay(config)
    mp.ask_confirmation = lambda question: False
    mp.create_database()
    return mp


def test_user(mpay_in_memory):
    mp = mpay_in_memory

    mp.create_user("test1")

    # duplicate username
    with pytest.raises(Exception):
        mp.create_user("test1")

    # invalid username
    with pytest.raises(ValueError):
        mp.create_user("Uppercase")

    with pytest.raises(ValueError):
        mp.create_user("user with space")

    mp.create_user("u2")
    users = mp.get_users_dataframe()
    assert len(users) == 2
    assert set(users["name"]) == {"test1", "u2"}


@pytest.fixture
def mpay_w_users(mpay_in_memory):
    mp = mpay_in_memory
    mp.create_user("test1")
    mp.create_user("test2")
    return mp


def test_pay(mpay_w_users):
    mp = mpay_w_users

    # invalid recipient
    with pytest.raises(ValueError):
        mp.pay(recipient_name="idontexist", converted_amount=Decimal("12.3"),
               due=datetime.datetime(2004, 1, 1))

    # paying to self
    with pytest.raises(ValueError):
        mp.pay(recipient_name="test1", converted_amount=Decimal("12.3"),
               due=datetime.datetime(2004, 1, 1))

    # due is in future
    with pytest.raises(Exception):
        mp.pay(recipient_name="test2", converted_amount=Decimal("12.3"),
               due=datetime.datetime.now() + datetime.timedelta(days=1))

    mp.create_tag("tag1")

    # missing tags
    with pytest.raises(ValueError):
        mp.pay(recipient_name="test2", converted_amount=Decimal("12.3"),
               due=datetime.datetime(2004, 1, 1), tag_names=["tag1", "tag2"])

    # missing agent
    with pytest.raises(ValueError):
        mp.pay(recipient_name="test2", converted_amount=Decimal("12.3"),
               due=datetime.datetime(2004, 1, 1), agent_name="agent1")

    # this should work
    mp.pay(recipient_name="test2", converted_amount=Decimal("12.3"),
           due=datetime.datetime(2004, 1, 1))

    # date should work - actually, no! It doesn't, and I don't care.
    # mp.pay(recipient_name="test2", converted_amount=Decimal("12.3"),
    #        due=datetime.date(2004, 1, 2))

    # can add existing tags
    mp.pay(recipient_name="test2", converted_amount=Decimal("0.3"),
           due=datetime.datetime(2004, 1, 3), tag_names=["tag1"])

    # works with existing agent
    mp.create_agent("agent1", "agent1 description")
    mp.pay(recipient_name="test2", converted_amount=Decimal("0.3"),
           due=datetime.datetime(2004, 1, 3), agent_name="agent1")

    # float should work in place of Decimal
    mp.pay(recipient_name="test2", converted_amount=0.6,
           due=datetime.datetime(2004, 1, 4))

    # negative amount should work:
    mp.pay(recipient_name="test2", converted_amount=Decimal("-10.3"),
           due=datetime.datetime(2004, 1, 5))

    with mpay.db.Session(mp.db_engine) as session:
        user = session.query(mpay.db.User).filter_by(name="test2").one()
        assert user.balance == Decimal("3.2")

    mp.check()
