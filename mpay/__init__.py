#!/usr/bin/env python3

from .cli import main
from .mpay import Mpay  # noqa: F401
from . import db


if __name__ == "__main__":
    main()
