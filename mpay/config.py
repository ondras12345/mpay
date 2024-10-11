import yaml
import os
import typing
import logging
from dataclasses import dataclass
from .const import (
    CONF_USER,
    CONF_DB_URL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class Config:
    user: str
    db_url: str
    # TODO base currency (default if --original is not specified)
    base_currency: str = "CZK"


def parse_config(file: typing.TextIO) -> Config:
    with file:
        config_dict = yaml.safe_load(file)
    if config_dict is None:
        config_dict = {}
    _LOGGER.debug("config_dict: %r", config_dict)

    user: str = config_dict.get(CONF_USER, os.getenv("USER"))

    config = Config(
        user=user,
        db_url=config_dict[CONF_DB_URL]
    )
    _LOGGER.debug("config: %r", config)
    return config
