import yaml
import os
import typing
import logging
import subprocess
import voluptuous as vol  # type: ignore
from dataclasses import dataclass
from typing import Any
from .const import (
    CONF_USER,
    CONF_DB_URL,
    CONF_COMMAND,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({
    vol.Required(CONF_DB_URL): vol.Any(
        vol.Exclusive(vol.All(str, vol.Length(min=1)), "db_url"),
        vol.Exclusive({
            vol.Required(CONF_COMMAND): vol.All(str, vol.Length(min=1))
        }, "db_url"),
    ),
    vol.Optional(CONF_USER, default=os.getenv("USER")):
        vol.All(str, vol.Length(min=1)),
})


@dataclass
class Config:
    user: str
    db_url: str
    # TODO base currency (default if --original is not specified)
    base_currency: str = "CZK"

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any]) -> "Config":
        config_dict = CONFIG_SCHEMA(config_dict)

        # db_url can either be a string, or it can specify a command to run to
        # retrieve the url from a password manager.
        db_url = config_dict[CONF_DB_URL]
        if isinstance(db_url, dict):
            db_url = subprocess.check_output(
                db_url[CONF_COMMAND],
                shell=True, text=True
            )

        c = cls(user=config_dict[CONF_USER], db_url=db_url)
        _LOGGER.debug("config: %r", c)
        return c

    @classmethod
    def from_yaml_file(cls, file: typing.TextIO) -> "Config":
        with file:
            config_dict = yaml.safe_load(file)
        if config_dict is None:
            config_dict = {}
        _LOGGER.debug("config_dict: %r", config_dict)
        return cls.from_dict(config_dict)
