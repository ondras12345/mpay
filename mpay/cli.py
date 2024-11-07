"""Command line interface for mpay."""

import logging
import datetime
import argparse
import argcomplete  # type: ignore
import pathlib
import os
import sys
import dateutil.rrule
import pandas as pd
import typing
import cmd
import shlex
from enum import Enum
from decimal import Decimal
from .config import Config
from .mpay import Mpay, MpayException
from .const import PROGRAM_NAME

_LOGGER = logging.getLogger(__name__)


class OutputFormat(Enum):
    JSON = "json"
    CSV = "csv"
    GUI = "gui"

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


def print_df(mp: Mpay, df: pd.DataFrame, output_format: OutputFormat | None, name: str | None = None):
    """Print a pandas dataframe in specified format."""
    match output_format:
        case OutputFormat.CSV:
            print(df.to_csv(index=False))

        case OutputFormat.JSON:
            print(df.to_json(orient="records", indent=2))

        case OutputFormat.GUI:
            from .gui import show_df, DfGUI, HistoryDfGUI
            view: typing.Any = DfGUI
            args = []
            if name == "history":
                view = HistoryDfGUI
                args = [mp.config.user]
            show_df(df, view, *args)

        case None:
            print(df.to_string(index=False))

        case _:
            raise NotImplementedError("unknown dataframe output format: %s", output_format)


def create_parser():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-f", "--format", type=OutputFormat, choices=list(OutputFormat),
        help="set output format for commands that output a pandas dataframe"
    )

    subparsers = parser.add_subparsers(dest="subparser_name", required=True)

    def pay(mp: Mpay, args):
        if args.original is None:
            args.original = (None, None)

        original_currency = args.original[0]
        original_amount = args.original[1]
        if original_amount is not None:
            original_amount = Decimal(original_amount)

        transaction_id = mp.pay(
            recipient_name=args.recipient,
            converted_amount=args.amount,
            original_currency=original_currency,
            original_amount=original_amount,
            agent_name=args.agent,
            due=args.due,
            note=args.note if args.note else None,  # map "" to None
            tag_hierarchical_names=args.tags
        )

        print(f"created transaction with id={transaction_id}")

    parser_pay = subparsers.add_parser(
        "pay",
        help="create a new transaction"
    )
    parser_pay.set_defaults(func_mpay=pay)

    parser_pay.add_argument(
        "--recipient", "--to", "-t", required=True,
        help="user to send the money to"
    )

    parser_pay.add_argument(
        "--amount", "-a", type=Decimal, required=True,
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

    # Note is optional in Mpay.pay, but most of the time if the user does not
    # specify it, it is because they forgot. I will make it required. If you
    # really want no note, specify --note ""
    parser_pay.add_argument(
        "--note", "-n", type=str, required=True
    )

    parser_pay.add_argument(
        "--tags",
        type=lambda t: [s.strip() for s in t.split(",")],
        default=[],
        help="comma separated list of tags (e.g. tag1,a/b/tag2)"
    )

    def history(mp: Mpay, args):
        print_df(mp, mp.get_transactions_dataframe(), args.format, "history")

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

    def tag_list(mp: Mpay, args):
        print_df(mp, mp.get_tags_dataframe(), args.format)

    parser_tag_list = subparsers_tag.add_parser(
        "list",
        help="list tags"
    )
    parser_tag_list.set_defaults(func_mpay=tag_list)

    def tag_tree(mp: Mpay, args):
        print(mp.get_tag_tree_str())

    parser_tag_tree = subparsers_tag.add_parser(
        "tree",
        help="print tag tree"
    )
    parser_tag_tree.set_defaults(func_mpay=tag_tree)

    def tag_create(mp: Mpay, args):
        mp.create_tag(
            tag_name=args.name,
            description=args.description,
            parent_hierarchical_name=args.parent
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
        help="hierarchical name of parent tag in tree structure"
    )

    def tag_add(mp: Mpay, args):
        mp.add_tags(
            transaction_ids=args.transactions,
            tag_hierarchical_names=args.tags,
        )

    parser_tag_add = subparsers_tag.add_parser(
        "add",
        help="add tags to existing transactions"
    )
    parser_tag_add.set_defaults(func_mpay=tag_add)

    parser_tag_add.add_argument(
        "--transactions",
        type=lambda t: [int(s) for s in t.split(",")],
        required=True,
        help="comma separated list of transaction ids"
    )

    parser_tag_add.add_argument(
        "--tags",
        type=lambda t: [s.strip() for s in t.split(",")],
        required=True,
        help="comma separated list of tags (e.g. tag1,a/b/tag2)"
    )

    def tag_remove(mp: Mpay, args):
        mp.remove_tags(
            transaction_ids=args.transactions,
            tag_hierarchical_names=args.tags
        )

    parser_tag_remove = subparsers_tag.add_parser(
        "remove",
        help="remove existing tags from existing transactions"
    )
    parser_tag_remove.set_defaults(func_mpay=tag_remove)

    parser_tag_remove.add_argument(
        "--transactions",
        type=lambda t: [int(s) for s in t.split(",")],
        required=True,
        help="comma separated list of transaction ids"
    )

    parser_tag_remove.add_argument(
        "--tags",
        type=lambda t: [s.strip() for s in t.split(",")],
        required=True,
        help="comma separated list of tags (e.g. tag1,a/b/tag2)"
    )

    def tag_show(mp: Mpay, args):
        tags = mp.get_tags_for_transaction(args.transaction_id)
        print("\n".join(tags))

    parser_tag_show = subparsers_tag.add_parser(
        "show",
        help="show tags linked to the specified transaction"
    )
    parser_tag_show.set_defaults(func_mpay=tag_show)

    parser_tag_show.add_argument(
        "transaction_id", type=int,
    )

    parser_order = subparsers.add_parser(
        "order",
        help="manage standing orders"
    )

    subparsers_order = parser_order.add_subparsers(required=True)

    def order_list(mp: Mpay, args):
        df = mp.get_orders_dataframe()
        if args.format is None:
            df.rrule_str = df.rrule_str.str.replace("\n", " ")
        print_df(mp, df, args.format)

    parser_order_list = subparsers_order.add_parser(
        "list",
        help="list standing orders"
    )
    parser_order_list.set_defaults(func_mpay=order_list)

    def order_create(mp: Mpay, args):
        mp.create_order(
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
        "--recipient", "--to", "-t", required=True,
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
        "--amount", "-a", type=Decimal, required=True,
        help="amount in base currency"
    )

    parser_order_create.add_argument(
        "--note", "-n", type=str
    )

    def order_disable(mp: Mpay, args) -> int:
        if mp.disable_order(args.name):
            return 0
        return 1

    parser_order_disable = subparsers_order.add_parser(
        "disable",
        help="disable an existing standing order. This operation is irreversible."
    )
    parser_order_disable.set_defaults(func_mpay=order_disable)

    parser_order_disable.add_argument(
        "name",
        help="name of standing order to be disabled"
    )

    parser_user = subparsers.add_parser(
        "user",
        help="manage users"
    )
    subparsers_user = parser_user.add_subparsers(required=True)

    def user_create(mp: Mpay, args):
        mp.create_user(args.username)

    parser_user_create = subparsers_user.add_parser(
        "create",
        help="create a new user"
    )
    parser_user_create.set_defaults(func_mpay=user_create)

    parser_user_create.add_argument(
        "username",
    )

    def user_list(mp: Mpay, args):
        print_df(mp, mp.get_users_dataframe(), args.format)

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

    def admin_check(mp: Mpay, args):
        mp.check()

    parser_admin_check = subparsers_admin.add_parser(
        "check",
        help="execute database checks"
    )
    parser_admin_check.set_defaults(func_mpay=admin_check)

    def admin_init(mp: Mpay, args):
        # handled by mpay_setup_database
        pass

    parser_admin_init = subparsers_admin.add_parser(
        "init",
        help="initialize the database"
    )
    parser_admin_init.set_defaults(func_mpay=admin_init,
                                   mpay_setup_database=True)

    def admin_cron(mp: Mpay, args):
        mp.execute_orders()

    parser_admin_cron = subparsers_admin.add_parser(
        "cron",
        help="execute periodic tasks (standing orders, etc.)"
    )
    parser_admin_cron.set_defaults(func_mpay=admin_cron)

    def admin_import(mp: Mpay, args):
        with args.csv_file as f:
            df = pd.read_csv(f, sep=args.delimiter)
        print(df)
        mp.import_df(
            df,
            user1_name=args.user1, user2_name=args.user2,
            agent_name="csvimport"
        )

    parser_admin_import = subparsers_admin.add_parser(
        "import",
        help="import transactions from csv"
    )
    parser_admin_import.set_defaults(func_mpay=admin_import)

    parser_admin_import.add_argument(
        "csv_file", type=argparse.FileType("r"),
        help="CSV file to import. Must contain header and the following columns: "
             "amount, dt_due, note"
    )

    parser_admin_import.add_argument(
        "--delimiter", type=str, default=",",
        help="csv file delimiter, default: %(default)r"
    )

    parser_admin_import.add_argument(
        "user1",
        help="name of user whose balance should be increased by "
             "a transaction with positive amount"
    )

    parser_admin_import.add_argument(
        "user2",
        help="name of user whose balance should be decreased by "
             "a transaction with positive amount"
    )

    return parser, subparsers


class InteractiveCLI(cmd.Cmd):
    doc_header = "Type -h to see help for mpay commands"

    def __init__(self, mp: Mpay, **kwargs):
        cmd.Cmd.__init__(self, **kwargs)

        self.mp = mp
        self.parser, _ = create_parser()

    def do_quit(self, args):
        """Exit the interactive CLI."""
        sys.exit()

    do_exit = do_quit
    do_EOF = do_quit

    def default(self, line):
        try:
            args = self.parser.parse_args(shlex.split(line))
        except SystemExit:
            return

        if hasattr(args, "func_mpay"):
            try:
                args.func_mpay(self.mp, args)
            except MpayException as e:
                print(f"error: {str(e)}")
        else:
            cmd.Cmd.default(self, line)


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

    parser, subparsers = create_parser()

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

    def interactive(mp: Mpay, args):
        icli = InteractiveCLI(mp)
        icli.cmdloop()

    # Interactive CLI keeps the database connection open, so it should respond
    # faster.
    parser_interactive = subparsers.add_parser(
        "interactive",
        help="enter interactive CLI"
    )
    parser_interactive.set_defaults(func_mpay=interactive)

    argcomplete.autocomplete(parser)

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

    try:
        config: Config = Config.from_yaml_file(args.config_file)
    except Exception as e:
        sys.exit(f"Error reading config file: {str(e)}")

    if args.override_user is not None:
        _LOGGER.warning("override user: %s", args.override_user)
        config.user = args.override_user

    _LOGGER.debug("config: %r", config)

    try:
        setup_db = bool(args.mpay_setup_database)
    except AttributeError:
        setup_db = False
    try:
        mp = Mpay(config, setup_db)
    except MpayException as e:
        sys.exit(f"Error: {str(e)}")
    if args.assume_no:
        mp.ask_confirmation = lambda question: False
    elif args.assume_yes:
        # leave default ask_confirmation
        pass
    else:
        mp.ask_confirmation = ask_confirmation

    try:
        ret = args.func_mpay(mp, args)
        sys.exit(ret if ret is not None else 0)
    # print "expected" Mpay exceptions w/o stack trace
    except MpayException as e:
        sys.exit(f"Error: {str(e)}")
    except Exception:
        _LOGGER.exception("unexpected exception")
        sys.exit("unexpected exception")
