#!/usr/bin/env python3
"""Mpay demo.

This scripts sets up an sqlite database and fills it with example data.
It also generates a mpay config file to allow subsequent interactive use.
"""

import mpay
import yaml
import pathlib
import dateutil.rrule
import datetime
import subprocess
from decimal import Decimal

# delete any database that might be there from previous runs
print("deleting old database")
demo_db = pathlib.Path("mpay-demo.db")
demo_db.unlink(missing_ok=True)

config_dict = {
    "user": "johndoe",
    "db_url": f"sqlite:///{demo_db}",
}

config_file = pathlib.Path("mpay-demo.yaml")
print(f"writing config to {config_file}")
with open(config_file, "w") as f:
    yaml.safe_dump(config_dict, f)

config = mpay.Config.from_dict(config_dict)

print("initializing database")
mp = mpay.Mpay(config, setup_database=True)

print("creating users")
mp.create_user(config.user)
mp.create_user("bob")
mp.create_user("alice")

print("creating transactions")
mp.pay(
    recipient_name="bob",
    converted_amount=Decimal("123.4"),
    note="first payment from johndoe to bob"
)

# from johndoe to alice with tags (will be created automatically)
mp.pay(
    recipient_name="alice",
    converted_amount=Decimal("12.3"),
    original_currency="EUR",
    original_amount=Decimal("0.492"),
    tag_hierarchical_names=(
        "examples/foreign_currency",
        "examples/tags",
    ),
    note="payment from johndoe to alice with tags and original_currency"
)

mp.pay(
    recipient_name="alice",
    converted_amount=Decimal("1.23"),
    agent_name="agent1",
    note="payment from johndoe to alice created by agent1"
)

print("creating standing orders")
start = (datetime.datetime.now()
         .replace(hour=0, minute=0, second=0, microsecond=0)
         - datetime.timedelta(days=4))

mp.create_order(
    name="order1",
    recipient_name="bob",
    amount=Decimal("1.0"),
    rrule=dateutil.rrule.rrule(freq=dateutil.rrule.DAILY, dtstart=start),
    note="recurring daily payment from johndoe to bob with no expiry"
)

mp.create_order(
    name="order2",
    recipient_name="alice",
    amount=Decimal("2.0"),
    rrule=dateutil.rrule.rrule(freq=dateutil.rrule.DAILY, dtstart=start, count=2),
    note="recurring daily payment from johndoe to alice with expiry after 2 occurences"
)

print("executing standing orders")
mp.execute_orders()

# this isn't really needed
print("checking database consistency")
mp.check()


print("done")
print(f"\nUse `mpay -c {config_file} ...` to play with the database interactively.")
print(f"\ne.g. mpay -c {config_file} user list:")
subprocess.run(["mpay", "-c", config_file, "user", "list"])
