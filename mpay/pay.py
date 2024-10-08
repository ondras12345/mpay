import logging
import mpay.db as db

_LOGGER = logging.getLogger(__name__)


def pay(*args, **kwargs):
    _LOGGER.debug("pay: %r %r", args, kwargs)
    # TODO
