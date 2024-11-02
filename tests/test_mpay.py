import pytest
import mpay
from mpay import MpayException, MpayValueError
import datetime
import dateutil.rrule
from decimal import Decimal


def test_init():
    config = mpay.Config(user="test1", db_url="sqlite:///")
    mp = mpay.Mpay(config, setup_database=True)

    mp.check()


@pytest.fixture
def mpay_in_memory():
    config = mpay.Config(user="test1", db_url="sqlite:///")
    mp = mpay.Mpay(config, setup_database=True)
    mp.ask_confirmation = lambda question: False
    return mp


@pytest.fixture
def mpay_w_users(mpay_in_memory):
    mp = mpay_in_memory
    mp.create_user("test1")
    mp.create_user("test2")
    return mp


def test_init_twice(mpay_in_memory):
    mp = mpay_in_memory
    # the currencies upsert should not fail:
    mpay.db.setup_database(mp.db_engine)


def test_check(mpay_in_memory):
    mp = mpay_in_memory

    mp.check()

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

    # Create the transaction. We need to change the balances first, since
    # creating the transaction will cause the trigger to fire.
    with mpay.db.Session(mp.db_engine) as session:
        u1 = session.query(mpay.db.User).filter_by(name="u1").one()
        u1.balance = 0
        session.add(u1)

        u2 = session.query(mpay.db.User).filter_by(name="u2").one()
        u2.balance = 0
        session.add(u2)

        # probably unnecessary
        session.flush()

        assert u1.balance == 0

        t = mpay.db.Transaction(user_from=u2, user_to=u1,
                                converted_amount=Decimal("12.3"),
                                dt_due_utc=mpay.db.aware_utcnow())
        session.add(t)

        # See if the User object got updated
        # TODO sqlalchemy ORM does not know the trigger ran, we need to expire
        # the User manually.
        session.expire(u1, ["balance"])
        assert u1.balance == Decimal("12.3")

        session.commit()

    # now it should be fixed
    mp.check()


def test_user(mpay_in_memory):
    mp = mpay_in_memory

    mp.create_user("test1")

    # duplicate username
    with pytest.raises(Exception):
        mp.create_user("test1")

    # invalid username
    with pytest.raises(MpayValueError):
        mp.create_user("Uppercase")

    with pytest.raises(MpayValueError):
        mp.create_user("user with space")

    mp.create_user("u2")
    users = mp.get_users_dataframe()
    assert len(users) == 2
    assert set(users["name"]) == {"test1", "u2"}


def test_pay(mpay_w_users):
    mp = mpay_w_users

    # invalid recipient
    with pytest.raises(MpayException):
        mp.pay(recipient_name="idontexist", converted_amount=Decimal("12.3"),
               due=datetime.datetime(2004, 1, 1))

    # paying to self
    with pytest.raises(MpayException):
        mp.pay(recipient_name="test1", converted_amount=Decimal("12.3"),
               due=datetime.datetime(2004, 1, 1))

    # due is in future
    with pytest.raises(Exception):
        mp.pay(recipient_name="test2", converted_amount=Decimal("12.3"),
               due=datetime.datetime.now() + datetime.timedelta(days=1))

    mp.create_tag("tag1")

    # missing tags
    with pytest.raises(MpayException):
        mp.pay(recipient_name="test2", converted_amount=Decimal("12.3"),
               due=datetime.datetime(2004, 1, 1), tag_hierarchical_names=["tag1", "tag2"])

    # missing agent
    with pytest.raises(MpayException):
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
           due=datetime.datetime(2004, 1, 3), tag_hierarchical_names=["tag1"])

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


def test_order(mpay_w_users):
    mp = mpay_w_users

    today = (
        # utcnow is deprecated
        # datetime.datetime.utcnow()
        datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )

    start_date = today - datetime.timedelta(days=5)

    # amount must be greater than zero
    with pytest.raises(MpayValueError):
        mp.create_order(name="order1", recipient_name="test2",
                        amount=Decimal("0"),
                        rrule=dateutil.rrule.rrule(freq=dateutil.rrule.DAILY))

    # sender must be different than recipient
    with pytest.raises(Exception):
        mp.create_order(name="order1", recipient_name="test1",
                        amount=Decimal("1"),
                        rrule=dateutil.rrule.rrule(freq=dateutil.rrule.DAILY))

    # this should work
    mp.create_order(
        name="order1", recipient_name="test2", amount=Decimal("1"),
        rrule=dateutil.rrule.rrule(freq=dateutil.rrule.DAILY, dtstart=start_date)
    )

    # order name must be unique (for this user)
    with pytest.raises(Exception):
        mp.create_order(name="order1", recipient_name="test2",
                        amount=Decimal(1),
                        rrule=dateutil.rrule.rrule(freq=dateutil.rrule.DAILY))

    # second order with limited duration
    mp.create_order(
        name="order2", recipient_name="test2", amount=Decimal("0.01"),
        rrule=dateutil.rrule.rrule(freq=dateutil.rrule.DAILY, count=3, dtstart=start_date)
    )

    with mpay.db.Session(mp.db_engine) as session:
        user = session.query(mpay.db.User).filter_by(name="test2").one()
        assert user.balance == Decimal("0")

    mp.execute_orders()

    mp.check()

    with mpay.db.Session(mp.db_engine) as session:
        user = session.query(mpay.db.User).filter_by(name="test2").one()
        assert user.balance == Decimal("6.03")

        o1 = session.query(mpay.db.StandingOrder).filter_by(name="order1").one()
        assert o1.dt_next_utc == today + datetime.timedelta(days=1)
        o2 = session.query(mpay.db.StandingOrder).filter_by(name="order2").one()
        assert o2.dt_next_utc is None

    assert not mp.disable_order("order1")
    mp.ask_confirmation = lambda question: True
    assert mp.disable_order("order1")

    with mpay.db.Session(mp.db_engine) as session:
        o1 = session.query(mpay.db.StandingOrder).filter_by(name="order1").one()
        assert o1.dt_next_utc is None


def test_delete_tag(mpay_w_users, caplog):
    # run pytest -o log_cli=true
    # import logging
    # caplog.set_level(logging.DEBUG)
    # caplog.set_level(logging.DEBUG, logger="sqlalchemy.engine")

    mp = mpay_w_users

    mp.create_tag("tag1")

    mp.pay(recipient_name="test2", converted_amount=Decimal("0.3"),
           due=datetime.datetime(2004, 1, 3), tag_hierarchical_names=["tag1"])

    with mpay.db.Session(mp.db_engine) as session:
        tag1 = session.query(mpay.db.Tag).filter_by(name="tag1").one()
        assert len(tag1.transactions) == 1
        transaction = tag1.transactions[0]
        assert transaction.tags == [tag1]

        # this should delete the tag without raising any exception
        session.delete(tag1)

        # The transaction should immediately know about it - or so I thought.
        # As it turns out, sqlalchemy will delete the transactions_tags
        # association even if I don't set ON DELETE CASCADE, but it does not
        # notify the transaction object for some reason.
        # assert transaction.tags == []

        session.commit()

    with mpay.db.Session(mp.db_engine) as session:
        tag1 = session.query(mpay.db.Tag).filter_by(name="tag1").one_or_none()
        assert tag1 is None

        transaction = session.query(mpay.db.Transaction).one()
        assert transaction.tags == []


def test_hierarchical_tag(mpay_w_users):
    mp = mpay_w_users

    # missing tags
    with pytest.raises(MpayException):
        mp.pay(recipient_name="test2", converted_amount=Decimal("12.3"),
               due=datetime.datetime(2004, 1, 1), tag_hierarchical_names=["tag1", "a/b/tag2"])

    # auto create
    mp.ask_confirmation = lambda question: True

    mp.pay(recipient_name="test2", converted_amount=Decimal("12.3"),
           due=datetime.datetime(2004, 1, 1), tag_hierarchical_names=["tag1", "a/b/tag2"])

    # /tag2 is not a duplicate of a/b/tag2:
    mp.pay(recipient_name="test2", converted_amount=Decimal("12.3"),
           due=datetime.datetime(2004, 1, 1), tag_hierarchical_names=["tag2"])

    with mpay.db.Session(mp.db_engine) as session:
        tag1 = session.query(mpay.db.Tag).filter_by(name="tag1").one()
        assert tag1.parent is None

        b = session.query(mpay.db.Tag).filter_by(name="b").one()
        a_b_tag2 = session.query(mpay.db.Tag).filter_by(name="tag2", parent=b).one()
        assert a_b_tag2.parent.name == "b"
        assert a_b_tag2.parent.parent.name == "a"
        assert a_b_tag2.parent.parent.parent is None
        assert a_b_tag2.hierarchical_name == "a/b/tag2"

        tag2 = session.query(mpay.db.Tag).filter_by(name="tag2", parent=None).one()
        assert tag2.hierarchical_name == "tag2"
