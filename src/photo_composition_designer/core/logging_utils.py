"""Minimal logging helpers replacing ``config_cli_gui.logging``.

Provides a process-wide initialized root logger and a ``get_logger`` helper.
File logging is intentionally omitted to keep the runtime dependency-free;
console logging via the standard library is sufficient for a local tool.
"""

from __future__ import annotations

import logging

_INITIALIZED = False


def initialize_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure the root logger once and return it."""
    global _INITIALIZED
    if not _INITIALIZED:
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        _INITIALIZED = True
    return logging.getLogger()


def get_logger(name: str = "photo_composition_designer") -> logging.Logger:
    """Return a named logger, initializing logging if needed."""
    if not _INITIALIZED:
        initialize_logging()
    return logging.getLogger(name)
