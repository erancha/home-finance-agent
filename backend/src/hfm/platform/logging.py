"""Process logging: structlog and standard-library records rendered through one stderr handler.

Core building blocks:
- configure_logging: root level from HFM_LOG_LEVEL (default WARNING), per-logger overrides from
  HFM_LOG_LEVELS ("name=LEVEL,name=LEVEL"), uvicorn's loggers routed to the shared handler
- ProbeAccessDemotion: drops successful /health and /ready access lines to DEBUG so frequent
  orchestrator probes do not flood the log
"""
from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping

import structlog

ENV_PREFIX = "HFM_"
DEFAULT_LEVEL = "WARNING"
PROBE_PATHS = frozenset({"/health", "/ready"})
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")
ACCESS_LOGGER = "uvicorn.access"

_SHARED_PROCESSORS: list[structlog.typing.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
]


class ProbeAccessDemotion(logging.Filter):
    """Uvicorn access records carry (client, method, path, http_version, status) as args."""

    def filter(self, record: logging.LogRecord) -> bool:
        assert isinstance(record.args, tuple), "uvicorn access records use positional args"
        path, status = record.args[2], record.args[4]
        assert isinstance(status, int), f"unexpected access status {status!r}"
        if path not in PROBE_PATHS or status >= 400:
            return True
        record.levelno, record.levelname = logging.DEBUG, logging.getLevelName(logging.DEBUG)
        return logging.getLogger(record.name).isEnabledFor(logging.DEBUG)


def parse_level_overrides(spec: str) -> dict[str, str]:
    """Parse "name=LEVEL,name=LEVEL"; a blank spec has no overrides."""
    overrides: dict[str, str] = {}
    for entry in filter(None, (part.strip() for part in spec.split(","))):
        name, separator, level = entry.partition("=")
        if not separator or not name or not level:
            raise ValueError(f"{ENV_PREFIX}LOG_LEVELS entry {entry!r} is not name=LEVEL")
        overrides[name.strip()] = level.strip().upper()
    return overrides


def configure_logging(env: Mapping[str, str] = os.environ) -> None:
    """Both level variables are optional; an unknown level name raises ValueError."""
    root_level = env.get(f"{ENV_PREFIX}LOG_LEVEL", DEFAULT_LEVEL).upper()
    overrides = parse_level_overrides(env.get(f"{ENV_PREFIX}LOG_LEVELS", ""))

    structlog.configure(
        processors=[*_SHARED_PROCESSORS, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        # Uncached, so a later reconfiguration (tests, a second app) reaches module-level loggers.
        cache_logger_on_first_use=False,
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
    ))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(root_level)
    # Uvicorn installs its own handlers and levels; reset them so its lines take the root level
    # and handler unless an override names them.
    for name in UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.NOTSET)
    for name, level in overrides.items():
        logging.getLogger(name).setLevel(level)
    access = logging.getLogger(ACCESS_LOGGER)
    access.filters[:] = [f for f in access.filters if not isinstance(f, ProbeAccessDemotion)]
    access.addFilter(ProbeAccessDemotion())
