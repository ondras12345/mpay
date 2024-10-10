#!/usr/bin/env python3

import datetime
import argparse
import yaml
import logging
import pathlib
import os

import mpay.pay as pay

_LOGGER = logging.getLogger(__name__)
PROGRAM_NAME: str = "mpay"

CONF_USER: str = "user"


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
    # TODO touch will change mtime if it already exists
    config_file.touch(exist_ok=True)

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
        "-v", "--verbose", action="count",
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
        "--amount", type=float, required=True,
        help="amount in base currency (CZK)"
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

    args = parser.parse_args()

    levels = {
        0: logging.WARNING,
        1: logging.INFO,
    }

    level = levels.get(args.verbose, logging.DEBUG)
    logging.basicConfig(level=level)
    _LOGGER.info("log verbosity: %s", logging.getLevelName(level))

    _LOGGER.debug("args: %r", args)

    with args.config_file as f:
        config = yaml.safe_load(f)
        if config is None:
            config = {}

    if args.override_user is not None:
        _LOGGER.warning("override user: %s", args.override_user)
        config[CONF_USER] = args.override_user

    _LOGGER.debug("config: %r", config)

    # db_conn = TODO

    match args.subparser_name:
        case "pay":
            if args.original is None:
                args.original = (None, None)
            # TODO catch exceptions
            pay.pay(
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
            raise NotImplementedError()

        case "order":
            raise NotImplementedError()

        case _:
            # this should never happen, unless someone forgot to implement it
            raise ValueError("invalid subparser")


if __name__ == "__main__":
    main()
