"""Log to a small rotating file in the user data folder."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .paths import log_file


def setup_logging() -> None:
    logger = logging.getLogger("oneclick")
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    try:
        path = log_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(path, maxBytes=256 * 1024, backupCount=2, encoding="utf-8")
    except OSError:
        handler = logging.NullHandler()  # logging must never stop the app from starting
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
