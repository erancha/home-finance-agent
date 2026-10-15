import logging

import pytest

from hfm.platform.logging import ACCESS_LOGGER as ACCESS
from hfm.platform.logging import configure_logging

pytestmark = pytest.mark.usefixtures("restore_logging")


def access_record(path: str, status: int) -> logging.LogRecord:
    return logging.LogRecord(
        ACCESS, logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", path, "1.1", status), None,
    )


def passes(record: logging.LogRecord) -> bool:
    """The logger's own level check runs before its filters, as in Logger.log."""
    logger = logging.getLogger(ACCESS)
    return logger.isEnabledFor(record.levelno) and bool(logger.filter(record))


def test_levels_come_from_hfm_prefixed_variables() -> None:
    configure_logging({
        "HFM_LOG_LEVEL": "INFO",
        "HFM_LOG_LEVELS": "hfm.application.review_graph=DEBUG",
        "LOG_LEVEL": "ERROR",
    })
    assert logging.getLogger().level == logging.INFO
    assert logging.getLogger("hfm.application.review_graph").level == logging.DEBUG


def test_root_level_defaults_to_warning() -> None:
    configure_logging({})
    assert logging.getLogger().level == logging.WARNING


def test_one_stderr_handler_carries_uvicorn_logs() -> None:
    configure_logging({})
    assert len(logging.getLogger().handlers) == 1
    for name in ("uvicorn", "uvicorn.error", ACCESS):
        logger = logging.getLogger(name)
        assert logger.handlers == []
        assert logger.propagate
        assert logger.level == logging.NOTSET


def test_override_can_raise_uvicorn_access_above_root() -> None:
    configure_logging({"HFM_LOG_LEVEL": "WARNING", "HFM_LOG_LEVELS": "uvicorn.access=INFO"})
    assert passes(access_record("/api/reviews", 202))
    assert not passes(access_record("/health", 200))


def test_malformed_override_fails_naming_the_entry() -> None:
    with pytest.raises(ValueError, match="hfm.adapters"):
        configure_logging({"HFM_LOG_LEVELS": "hfm.adapters"})


def test_unknown_level_fails() -> None:
    with pytest.raises(ValueError):
        configure_logging({"HFM_LOG_LEVEL": "LOUD"})


def test_successful_probe_access_lines_are_demoted_to_debug() -> None:
    configure_logging({"HFM_LOG_LEVEL": "INFO"})
    health = access_record("/health", 200)
    assert not passes(health)
    assert health.levelno == logging.DEBUG
    assert not passes(access_record("/ready", 200))


def test_failed_probes_and_other_paths_keep_their_level() -> None:
    configure_logging({"HFM_LOG_LEVEL": "INFO"})
    assert passes(access_record("/ready", 503))
    assert passes(access_record("/api/reviews", 202))


def test_demoted_probe_lines_show_at_debug() -> None:
    configure_logging({"HFM_LOG_LEVEL": "DEBUG"})
    assert passes(access_record("/health", 200))
