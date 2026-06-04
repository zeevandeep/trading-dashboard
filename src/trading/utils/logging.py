"""Logging setup — console + file output with timestamps."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from trading.config import LOGS_DIR


def setup_logging(name: str = "trading", log_to_file: bool = True) -> logging.Logger:
    """Return a logger configured for console + optional file output."""
    logger = logging.getLogger(name)

    # Avoid duplicate handlers on re-initialization
    if logger.handlers:
        return logger

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.setLevel(level)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File (daily rotation by filename)
    if log_to_file:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOGS_DIR / f"{datetime.now().strftime('%Y%m%d')}_{name}.log"
        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger
