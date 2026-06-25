"""Tests for ascii_pet.log module (loguru-based logging initialization).

Covers setup_logging() scenarios from spec:
- File sink creation and message writing
- data_dir=None fallback to _default_data_dir()
- Directory creation failure graceful degradation
- console=False (file-only) configuration
- Idempotent repeated calls (no sink stacking)
- Global logger singleton identity
- Log file rotation with compression (slow)
- Log format contains timestamp and level
- logger.exception() captures traceback
"""
import os
import re
import sys
import time
from pathlib import Path

import pytest
from loguru import logger as loguru_logger

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.log import setup_logging, logger


@pytest.fixture(autouse=True)
def _clean_loguru_handlers():
    """Clear all loguru sinks before and after each test for isolation."""
    logger.remove()
    yield
    logger.remove()


def test_setup_logging_creates_log_file(tmp_path):
    """setup_logging(data_dir=tmp_path) creates tmp_path/logs/ascii-pet.log."""
    setup_logging(data_dir=tmp_path, console=False)
    logger.info("trigger file creation")
    logger.complete()
    log_file = tmp_path / "logs" / "ascii-pet.log"
    assert log_file.exists()


def test_setup_logging_writes_log_message(tmp_path):
    """setup_logging writes log messages to the file."""
    setup_logging(data_dir=tmp_path, console=False)
    logger.info("test message")
    logger.complete()
    log_file = tmp_path / "logs" / "ascii-pet.log"
    content = log_file.read_text(encoding="utf-8")
    assert "test message" in content


def test_setup_logging_data_dir_none_fallback(monkeypatch, tmp_path):
    """setup_logging(data_dir=None) falls back to _default_data_dir() without raising."""
    monkeypatch.setattr("ascii_pet.core._default_data_dir", lambda: tmp_path)
    setup_logging(data_dir=None, console=False)
    logger.info("fallback test")
    logger.complete()
    log_file = tmp_path / "logs" / "ascii-pet.log"
    assert log_file.exists()


def test_setup_logging_directory_creation_failure_fallback(monkeypatch, tmp_path):
    """setup_logging falls back to console-only when directory creation fails."""
    def raise_oserror(self, *args, **kwargs):
        raise OSError("permission denied")
    monkeypatch.setattr("pathlib.Path.mkdir", raise_oserror)
    # Should not raise
    setup_logging(data_dir=tmp_path, console=True)
    # Only console sink should be configured (file sink failed)
    assert len(logger._core.handlers) == 1


def test_setup_logging_console_false(tmp_path):
    """setup_logging(console=False) configures only file sink."""
    setup_logging(data_dir=tmp_path, console=False)
    assert len(logger._core.handlers) == 1


def test_setup_logging_idempotent(tmp_path):
    """Repeated setup_logging calls don't stack sinks."""
    setup_logging(data_dir=tmp_path, console=False)
    count1 = len(logger._core.handlers)
    setup_logging(data_dir=tmp_path, console=False)
    count2 = len(logger._core.handlers)
    assert count1 == count2 == 1


def test_get_logger_returns_loguru_logger():
    """from ascii_pet.log import logger returns the loguru singleton."""
    assert logger is loguru_logger


@pytest.mark.slow
def test_log_file_rotation(tmp_path):
    """Log file rotates when exceeding rotation size, producing .zip archive."""
    setup_logging(data_dir=tmp_path, console=False)
    # Write >1MB to trigger rotation on next write
    big_msg = "x" * (1024 * 1024 + 100)
    logger.info(big_msg)
    # This message triggers rotation (file size > 1MB)
    logger.info("trigger rotation")
    logger.complete()
    # Allow compression thread to finish
    time.sleep(1.0)
    log_dir = tmp_path / "logs"
    zip_files = list(log_dir.glob("*.zip"))
    assert len(zip_files) >= 1


def test_log_format_contains_timestamp_and_level(tmp_path):
    """Log format includes timestamp and level."""
    setup_logging(data_dir=tmp_path, console=False)
    logger.info("format test")
    logger.complete()
    log_file = tmp_path / "logs" / "ascii-pet.log"
    content = log_file.read_text(encoding="utf-8")
    # Timestamp pattern: YYYY-MM-DD HH:MM:SS.SSS
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}", content)
    # Level
    assert "INFO" in content


def test_log_exception_captures_traceback(tmp_path):
    """logger.exception() captures traceback in log file."""
    setup_logging(data_dir=tmp_path, console=False)
    try:
        raise ValueError("test error for traceback")
    except ValueError:
        logger.exception("caught error")
    logger.complete()
    log_file = tmp_path / "logs" / "ascii-pet.log"
    content = log_file.read_text(encoding="utf-8")
    assert "Traceback" in content
    assert "ValueError" in content
    assert "test error for traceback" in content
