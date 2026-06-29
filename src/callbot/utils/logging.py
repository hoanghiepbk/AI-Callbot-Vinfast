"""Structured logging setup.

Library code only calls ``logging.getLogger(__name__)``; it never configures the root logger.
The application entry point calls :func:`setup_logging` once so those records actually surface
(with timestamps + level + module), and per-turn latency lines (see :mod:`callbot.utils.latency`)
become visible. Idempotent, so calling it more than once is harmless.
"""

from __future__ import annotations

import logging
import os

_configured = False


def setup_logging(level: str | int | None = None) -> None:
    """Configure root logging once. Level from the arg, else LOG_LEVEL env, else INFO."""
    global _configured
    if _configured:
        return
    resolved = level if level is not None else os.environ.get("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=resolved,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    _configured = True
