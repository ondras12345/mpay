import yaml
import os
import typing
import logging
import subprocess
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

    @classmethod
    def from_dict(cls, config_dict: dict):
        # TODO validate

        user: str = config_dict.get(CONF_USER, os.getenv("USER"))

        # db_url can either be a string, or it can specify a command to run to
        # retrieve the url from a password manager.
        db_url = config_dict[CONF_DB_URL]
        if isinstance(db_url, dict):
            db_url = subprocess.check_output(
                db_url.get("command"),
                shell=True, text=True
            )

        config = cls(user=user, db_url=db_url)
        _LOGGER.debug("config: %r", config)
        return config

    @classmethod
    def from_yaml_file(cls, file: typing.TextIO):
        with file:
            config_dict = yaml.safe_load(file)
        if config_dict is None:
            config_dict = {}
        _LOGGER.debug("config_dict: %r", config_dict)

        return cls.from_dict(config_dict)
