"""Tests for dispatch.print_watcher (written TDD — before the implementation)."""
import logging
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dispatch.print_watcher import watch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def inbox(tmp_path):
    """Return a config dict pointing at a temp inbox with a PRINTED/ subfolder."""
    print_dir = tmp_path / "PRINT"
    (print_dir / "PRINTED").mkdir(parents=True)
    config = {"watch": {"print_dir": str(print_dir)}}
    return config, print_dir


@pytest.fixture()
def logger():
    return logging.getLogger("test_print")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _place_pdf(directory: Path, name: str = "test.pdf") -> Path:
    f = directory / name
    f.write_bytes(b"%PDF-1.4 fake content")
    return f


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_pdf_detected(inbox, logger):
    """A .pdf file in the inbox is included in the candidate list processed by watch."""
    config, print_dir = inbox
    pdf = _place_pdf(print_dir)

    processed = []

    with patch("dispatch.print_watcher.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr=b"")
        with patch("dispatch.print_watcher.fcntl.flock"):  # don't actually lock
            watch(config, logger)

    # After a successful run the file should have moved to PRINTED/
    assert not pdf.exists(), "PDF should have been moved out of the inbox"
    assert (print_dir / "PRINTED" / "test.pdf").exists()


def test_non_pdf_ignored(inbox, logger):
    """Non-.pdf files in the inbox are ignored by the watcher."""
    config, print_dir = inbox
    txt = print_dir / "readme.txt"
    txt.write_text("not a pdf")

    with patch("dispatch.print_watcher.subprocess.run") as mock_run:
        with patch("dispatch.print_watcher.fcntl.flock"):
            watch(config, logger)

    mock_run.assert_not_called()
    assert txt.exists(), "Non-PDF should remain untouched"


def test_locked_file_skipped(inbox, logger, caplog):
    """A PDF whose lock cannot be acquired is skipped; lp is not called."""
    config, print_dir = inbox
    _place_pdf(print_dir)

    with patch("dispatch.print_watcher.subprocess.run") as mock_run:
        with patch("dispatch.print_watcher.fcntl.flock", side_effect=BlockingIOError):
            with caplog.at_level(logging.WARNING, logger="test_print"):
                watch(config, logger)

    mock_run.assert_not_called()
    assert any("lock" in r.message.lower() or "skip" in r.message.lower() for r in caplog.records)


def test_successful_print_moves_file(inbox, logger, caplog):
    """A successful lp command causes the file to be moved to PRINTED/ and INFO is logged."""
    config, print_dir = inbox
    pdf = _place_pdf(print_dir)

    with patch("dispatch.print_watcher.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr=b"")
        with patch("dispatch.print_watcher.fcntl.flock"):
            with caplog.at_level(logging.INFO, logger="test_print"):
                watch(config, logger)

    assert not pdf.exists()
    assert (print_dir / "PRINTED" / "test.pdf").exists()
    assert any(r.levelno == logging.INFO for r in caplog.records)


def test_failed_print_leaves_file(inbox, logger, caplog):
    """A failing lp command leaves the file in the inbox and logs an ERROR."""
    config, print_dir = inbox
    pdf = _place_pdf(print_dir)

    with patch("dispatch.print_watcher.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr=b"printer offline")
        with patch("dispatch.print_watcher.fcntl.flock"):
            with caplog.at_level(logging.ERROR, logger="test_print"):
                watch(config, logger)

    assert pdf.exists(), "File should remain in inbox after failed print"
    assert not (print_dir / "PRINTED" / "test.pdf").exists()
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_destination_already_exists(inbox, logger):
    """When PRINTED/test.pdf already exists, the move silently overwrites it (documents overwrite-on-collision behaviour)."""
    config, print_dir = inbox
    pdf = _place_pdf(print_dir)
    # Pre-place a file with the same name in the destination directory.
    _place_pdf(print_dir / "PRINTED")

    with patch("dispatch.print_watcher.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr=b"")
        with patch("dispatch.print_watcher.fcntl.flock"):
            watch(config, logger)

    assert not pdf.exists(), "PDF should have been moved out of the inbox"
    assert (print_dir / "PRINTED" / "test.pdf").exists()
