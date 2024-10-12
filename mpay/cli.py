import logging
import datetime
import argparse
import pathlib
import os
import sys
import dateutil.rrule
import pandas as pd
from enum import Enum
from decimal import Decimal
from .config import Config, parse_config
from .mpay import Mpay
from .const import PROGRAM_NAME

_LOGGER = logging.getLogger(__name__)


class OutputFormat(Enum):
    JSON = "json"
    CSV = "csv"

    def __str__(self):
        return self.value


def strtobool(val: str) -> bool:
    """Convert a string representation of truth to True or False.
    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    val = val.lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return True
    elif val in ('n', 'no', 'f', 'false', 'off', '0'):
        return False
    else:
        raise ValueError(f"invalid truth value {repr(val)}")


def ask_confirmation(question: str) -> bool:
    default = False
    yn = {
        None: "[y/n]",
        True: "[Y/n]",
        False: "[y/N]",
    }
    while True:
        try:
            choice = input(f"{question} {yn[default]} ")
        except EOFError:
            if default is None:
                raise
            return default
        if choice == "" and default is not None:
            return default
        try:
            return strtobool(choice.lower())
        except ValueError:
            print(f"invalid choice: {choice}")


def print_df(df: pd.DataFrame, output_format: OutputFormat | None):
    """Print a pandas dataframe in specified format."""
    match output_format:
        case OutputFormat.CSV:
            print(df.to_csv(index=False))

        case OutputFormat.JSON:
            print(df.to_json(orient="records", indent=2))

        case None:
            print(df.to_string(index=False))

        case _:
            raise NotImplementedError("unknown dataframe output format: %s", output_format)


def main():
    config_dir = pathlib.Path(
            os.environ.get("APPDATA") or
            os.environ.get("XDG_CONFIG_HOME") or
            os.path.join(os.environ["HOME"], ".config"),
        ) / PROGRAM_NAME

    config_file = config_dir / "config.yaml"
    # ensure config file exists
    config_dir.mkdir(parents=True, exist_ok=True)
    if not config_file.exists():
        config_file.touch()

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-c", "--config-file",
        help="path to configuration file (default %(default)s)",
        type=argparse.FileType("r"),
        default=str(config_file)
    )

    parser.add_argument(
        "--override-user",
        type=str, metavar="USER",
        help="execute action as USER"
    )

    parser.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="increase verbosity. Can be provided up to two times."
    )

    parser.add_argument(
        "-y", "--assume-yes", "--yes",
        action="store_true",
        help='assume "yes" as answer to all prompts and run non-interactively'
    )

    parser.add_argument(
        "--assume-no", "--no",
        action="store_true",
        help='assume "no" as answer to all prompts and run non-interactively. '
             "This is roughly equivalent to reading EOF from stdin, "
             "but it does not print the prompts"
    )

    parser.add_argument(
        "--format", type=OutputFormat, choices=list(OutputFormat),
        help="set output format for commands that output a pandas dataframe"
    )

    subparsers = parser.add_subparsers(dest="subparser_name", required=True)

    def pay(mpay: Mpay, args):
        if args.original is None:
            args.original = (None, None)

        original_currency = args.original[0]
        original_amount = args.original[1]
        if original_amount is not None:
            original_amount = Decimal(original_amount)

        mpay.pay(
            recipient_name=args.recipient,
            converted_amount=args.amount,
            original_currency=original_currency,
            original_amount=original_amount,
            agent_name=args.agent,
            due=args.due,
            note=args.note,
            tag_names=args.tags
        )

    parser_pay = subparsers.add_parser(
        "pay",
        help="create a new transaction"
    )
    parser_pay.set_defaults(func_mpay=pay)

    parser_pay.add_argument(
        "--recipient", "--to", required=True,
        help="user to send the money to"
    )

    parser_pay.add_argument(
        "--amount", type=Decimal, required=True,
        help="amount in base currency"
    )

    parser_pay.add_argument(
        "--original",
        nargs=2, metavar=("CURRENCY", "AMOUNT"),
        help="Original amount and currency."
    )

    parser_pay.add_argument(
        "--agent", type=str,
        help="agent that created this payment"
    )

    parser_pay.add_argument(
        "--due", type=datetime.datetime.fromisoformat,
        default=datetime.datetime.now(),
        help="due date of this payment in ISO8601 format. Default: now"
    )

    parser_pay.add_argument(
        "--note", type=str
    )

    parser_pay.add_argument(
        "--tags",
        type=lambda t: [s.strip() for s in t.split(",")],
        help="comma separated list of tags"
    )

    def history(mpay: Mpay, args):
        raise NotImplementedError("TODO")

    parser_history = subparsers.add_parser(
        "history",
        help="print transaction history"
    )
    parser_history.set_defaults(func_mpay=history)

    parser_tag = subparsers.add_parser(
        "tag",
        help="manage tags"
    )

    subparsers_tag = parser_tag.add_subparsers(required=True)

    def tag_list(mpay: Mpay, args):
        print_df(mpay.get_tags_dataframe(), args.format)

    parser_tag_list = subparsers_tag.add_parser(
        "list",
        help="list tags"
    )
    parser_tag_list.set_defaults(func_mpay=tag_list)

    def tag_tree(mpay: Mpay, args):
        print(mpay.get_tag_tree_str())

    parser_tag_tree = subparsers_tag.add_parser(
        "tree",
        help="print tag tree"
    )
    parser_tag_tree.set_defaults(func_mpay=tag_tree)

    def tag_create(mpay: Mpay, args):
        mpay.create_tag(
            tag_name=args.name,
            description=args.description,
            parent_name=args.parent
        )

    parser_tag_create = subparsers_tag.add_parser(
        "create",
        help="create a new tag"
    )
    parser_tag_create.set_defaults(func_mpay=tag_create)

    parser_tag_create.add_argument(
        "name"
    )

    parser_tag_create.add_argument(
        "description", nargs="?", default=None
    )

    parser_tag_create.add_argument(
        "--parent",
        help="parent tag in tree structure"
    )

    parser_order = subparsers.add_parser(
        "order",
        help="manage standing orders"
    )

    subparsers_order = parser_order.add_subparsers(required=True)

    def order_list(mpay: Mpay, args):
        raise NotImplementedError("TODO")

    parser_order_list = subparsers_order.add_parser(
        "list",
        help="list standing orders"
    )
    parser_order_list.set_defaults(func_mpay=order_list)

    def order_create(mpay: Mpay, args):
        mpay.create_order(
            name=args.order_name,
            recipient_name=args.recipient,
            amount=args.amount,
            rrule=args.rrule,
            note=args.note,
        )

    parser_order_create = subparsers_order.add_parser(
        "create",
        help="create a new standing order"
    )
    parser_order_create.set_defaults(func_mpay=order_create)

    parser_order_create.add_argument(
        "order_name",
        help="standing order name"
    )

    parser_order_create.add_argument(
        "--recipient", "--to", required=True,
        help="user to send the money to"
    )

    parser_order_create.add_argument(
        "--rrule", required=True,
        type=lambda s: dateutil.rrule.rrulestr(
            s,
            # default dtstart: today's midnight
            dtstart=datetime.datetime.now()
            .replace(hour=0, minute=0, second=0, microsecond=0)
        ),
        help="recurrence rule in iCal RRULE format. "
             "DTSTART will be interpreted as UTC datetime."
    )

    parser_order_create.add_argument(
        "--amount", type=Decimal, required=True,
        help="amount in base currency"
    )

    parser_order_create.add_argument(
        "--note", type=str
    )

    def order_disable(mpay: Mpay, args):
        raise NotImplementedError("TODO")

    parser_order_disable = subparsers_order.add_parser(
        "disable",
        help="disable an existing standing order"
    )
    parser_order_disable.set_defaults(func_mpay=order_disable)

    parser_user = subparsers.add_parser(
        "user",
        help="manage users"
    )
    subparsers_user = parser_user.add_subparsers(required=True)

    def user_create(mpay: Mpay, args):
        mpay.create_user(args.username)

    parser_user_create = subparsers_user.add_parser(
        "create",
        help="create a new user"
    )
    parser_user_create.set_defaults(func_mpay=user_create)

    parser_user_create.add_argument(
        "username",
    )

    def user_list(mpay: Mpay, args):
        print_df(mpay.get_users_dataframe(), args.format)

    parser_user_list = subparsers_user.add_parser(
        "list",
        help="list users"
    )
    parser_user_list.set_defaults(func_mpay=user_list)

    parser_admin = subparsers.add_parser(
        "admin",
        help="perform administrative tasks that require elevated permissions"
    )
    subparsers_admin = parser_admin.add_subparsers(required=True)

    def admin_check(mpay: Mpay, args):
        mpay.check()

    parser_admin_check = subparsers_admin.add_parser(
        "check",
        help="execute database checks"
    )
    parser_admin_check.set_defaults(func_mpay=admin_check)

    def admin_init(mpay: Mpay, args):
        mpay.create_database()

    parser_admin_init = subparsers_admin.add_parser(
        "init",
        help="initialize the database"
    )
    parser_admin_init.set_defaults(func_mpay=admin_init)

    def admin_cron(mpay: Mpay, args):
        mpay.execute_orders()

    parser_admin_cron = subparsers_admin.add_parser(
        "cron",
        help="execute periodic tasks (standing orders, etc.)"
    )
    parser_admin_cron.set_defaults(func_mpay=admin_cron)

    args = parser.parse_args()

    levels = {
        0: logging.WARNING,
        1: logging.INFO,
    }

    level = levels.get(args.verbose, logging.DEBUG)
    logging.basicConfig(level=level)
    _LOGGER.info("log verbosity: %s", logging.getLevelName(level))
    logging.getLogger("sqlalchemy.engine").setLevel(level)

    _LOGGER.debug("args: %r", args)

    if not args.func_mpay:
        raise NotImplementedError("this might be needed for commands that should not connect to the db")

    config: Config = parse_config(args.config_file)

    if args.override_user is not None:
        _LOGGER.warning("override user: %s", args.override_user)
        config.user = args.override_user

    _LOGGER.debug("config: %r", config)

    mpay = Mpay(config)
    if args.assume_no:
        mpay.ask_confirmation = lambda x: False
    elif args.assume_yes:
        # leave default ask_confirmation
        pass
    else:
        mpay.ask_confirmation = ask_confirmation

    try:
        args.func_mpay(mpay, args)
        sys.exit(0)
    # print "expected" Mpay exceptions w/o stack trace
    except ValueError as e:
        print(f"Error: {str(e)}")
        sys.exit(1)
    except Exception:
        _LOGGER.exception("unexpected exception")
        sys.exit(1)
