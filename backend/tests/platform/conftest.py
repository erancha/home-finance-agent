import logging
from collections.abc import Iterator

import pytest
import structlog

from hfm.platform.logging import UVICORN_LOGGERS


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """Undo configure_logging's process-wide changes so later tests see pytest's setup."""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    touched = ["hfm.application.review_graph", *UVICORN_LOGGERS]
    saved = {name: logging.getLogger(name) for name in touched}
    saved_state = {
        name: (lg.level, lg.handlers[:], lg.propagate, lg.filters[:]) for name, lg in saved.items()
    }
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    for name, (level, handlers, propagate, filters) in saved_state.items():
        logger = saved[name]
        logger.setLevel(level)
        logger.handlers[:] = handlers
        logger.propagate = propagate
        logger.filters[:] = filters
    structlog.reset_defaults()
