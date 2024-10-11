import logging
import datetime
import argparse
import pathlib
import os
from decimal import Decimal
from .config import Config, parse_config
from .mpay import Mpay
from .const import PROGRAM_NAME

_LOGGER = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()

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
        "-y", "--yes", "--assume-yes",
        action="store_true",
        help='assume "yes" as answer to all prompts and run non-interactively'
    )

    subparsers = parser.add_subparsers(dest="subparser_name", required=True)

    parser_pay = subparsers.add_parser(
        "pay",
        help="create a new transaction"
    )

    parser_pay.add_argument(
        "--recipient", "--to", required=True,
        help="user to send the money to"
    )

    parser_pay.add_argument(
        "--amount", type=Decimal, required=True,
        help="amount in base currency (CZK)"
    )

    parser_pay.add_argument(
        "--original",
        nargs=2, metavar=("CURRENCY", "AMOUNT"),
        # TODO type
        help="Original amount and currency."
    )

    parser_pay.add_argument(
        "--agent", type=str,
        help="agent that created this payment"
    )

    parser_pay.add_argument(
        "--due", type=datetime.datetime.fromisoformat,
        default=datetime.datetime.now(),
        help="due date of this payment is ISO8601 format. Default: now"
    )

    parser_pay.add_argument(
        "--note", type=str
    )

    parser_pay.add_argument(
        "--tags",
        type=lambda t: [s.strip() for s in t.split(",")],
        help="comma separated list of tags"
    )

    parser_history = subparsers.add_parser(
        "history",
        help="print transaction history"
    )

    parser_tag = subparsers.add_parser(
        "tag",
        help="manage tags"
    )

    subparsers_tag = parser_tag.add_subparsers(dest="subparser_tag_name", required=True)

    parser_tag_list = subparsers_tag.add_parser(
        "list",
        help="list tags"
    )

    parser_tag_create = subparsers_tag.add_parser(
        "create",
        help="create a new tag"
    )

    parser_tag_create.add_argument(
        "tag_name"
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

    subparsers_order = parser_order.add_subparsers(dest="subparser_order_name", required=True)

    parser_order_list = subparsers_order.add_parser(
        "list",
        help="list standing orders"
    )

    parser_order_create = subparsers_order.add_parser(
        "create",
        help="create a new standing order"
    )

    parser_order_modify = subparsers_order.add_parser(
        "modify",
        help="modify an existing standing order"
    )

    parser_user = subparsers.add_parser(
        "user",
        help="manage users"
    )

    subparsers_user = parser_user.add_subparsers(dest="subparser_user_name", required=True)

    parser_user_create = subparsers_user.add_parser(
        "create",
        help="create a new user"
    )

    parser_user_create.add_argument(
        "username",
    )

    parser_user_list = subparsers_user.add_parser(
        "list",
        help="list users"
    )

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

    config: Config = parse_config(args.config_file)

    if args.override_user is not None:
        _LOGGER.warning("override user: %s", args.override_user)
        config.user = args.override_user

    _LOGGER.debug("config: %r", config)

    mpay = Mpay(config)

    match args.subparser_name:
        # TODO exec_orders (cron)
        case "pay":
            if args.original is None:
                args.original = (None, None)
            # TODO catch exceptions
            mpay.pay(
                recipient=args.recipient,
                converted_amount=args.amount,
                original_currency=args.original[0],
                original_amount=args.original[1],
                agent=args.agent,
                due=args.due,
                note=args.note,
                tags=args.tags
            )

        case "history":
            raise NotImplementedError()

        case "tag":
            match args.subparser_tag_name:
                case "list":
                    print(mpay.get_tags_dataframe())
                    #for t in tags:
                    #    print(t.id, t.name, t.parent_id, t.description)
                case "create":
                    mpay.create_tag(tag_name=args.tag_name,
                                    description=args.description,
                                    parent_name=args.parent)
                case _:
                    raise NotImplementedError()

        case "order":
            raise NotImplementedError()

        case "user":
            match args.subparser_user_name:
                case "create":
                    mpay.create_user(args.username)

                case "list":
                    # TODO pandas, output formats (json, csv, ...)?
                    users = mpay.get_users()
                    for u in users:
                        print(u.id, u.name, u.balance)

                case _:
                    raise NotImplementedError()

        case _:
            # this should never happen, unless someone forgot to implement it
            raise ValueError("invalid subparser")
