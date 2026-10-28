"""Logging configuration: console output plus a rotating log file in the data folder."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE = "arcade.log"


def setup_logging(data_dir: Path, level: int = logging.INFO) -> Path | None:
    """Configure the root logger. Returns the log file path, or ``None`` if unwritable."""
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    path = data_dir / LOG_FILE
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(path, maxBytes=512_000, backupCount=2, encoding="utf-8")
    except OSError:
        root.warning("Could not open log file at %s; logging to console only", path)
        return None
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    return path
