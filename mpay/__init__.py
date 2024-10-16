#!/usr/bin/env python3

from .cli import main
from .mpay import Mpay  # noqa: F401
from .config import Config  # noqa: F401
from . import db  # noqa: F401


if __name__ == "__main__":
    main()
