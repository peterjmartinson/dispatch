"""Tests for dispatch.email_watcher (written TDD — before the implementation)."""
import logging
import smtplib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dispatch.email_watcher import watch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def inbox(tmp_path):
    """Return a config dict pointing at a temp inbox with a SENT/ subfolder."""
    email_dir = tmp_path / "EMAIL"
    (email_dir / "SENT").mkdir(parents=True)
    config = {
        "watch": {"email_dir": str(email_dir)},
        "email": {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "username": "test@example.com",
            "password": "secret",
            "from_addr": "test@example.com",
            "to_addr": "dest@example.com",
            "subject_prefix": "TestPrefix",
        },
    }
    return config, email_dir


@pytest.fixture()
def logger():
    return logging.getLogger("test_email")


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
    """A .pdf file in the inbox is processed (sent and moved) by watch."""
    config, email_dir = inbox
    pdf = _place_pdf(email_dir)

    mock_smtp = MagicMock()
    with patch("dispatch.email_watcher.smtplib.SMTP", return_value=mock_smtp):
        with patch("dispatch.email_watcher.fcntl.flock"):
            watch(config, logger)

    assert not pdf.exists()
    assert any((email_dir / "SENT").glob("test.*.pdf"))


def test_non_pdf_ignored(inbox, logger):
    """Non-.pdf files in the inbox are ignored by the watcher."""
    config, email_dir = inbox
    txt = email_dir / "notes.txt"
    txt.write_text("not a pdf")

    with patch("dispatch.email_watcher.smtplib.SMTP") as mock_smtp_cls:
        with patch("dispatch.email_watcher.fcntl.flock"):
            watch(config, logger)

    mock_smtp_cls.assert_not_called()
    assert txt.exists()


def test_locked_file_skipped(inbox, logger, caplog):
    """A PDF whose lock cannot be acquired is skipped; SMTP is not called."""
    config, email_dir = inbox
    _place_pdf(email_dir)

    with patch("dispatch.email_watcher.smtplib.SMTP") as mock_smtp_cls:
        with patch("dispatch.email_watcher.fcntl.flock", side_effect=BlockingIOError):
            with caplog.at_level(logging.WARNING, logger="test_email"):
                watch(config, logger)

    mock_smtp_cls.assert_not_called()
    assert any("lock" in r.message.lower() or "skip" in r.message.lower() for r in caplog.records)


def test_successful_send_moves_file(inbox, logger, caplog):
    """A successful SMTP send moves the file to SENT/ and logs INFO."""
    config, email_dir = inbox
    pdf = _place_pdf(email_dir)

    mock_smtp = MagicMock()
    with patch("dispatch.email_watcher.smtplib.SMTP", return_value=mock_smtp):
        with patch("dispatch.email_watcher.fcntl.flock"):
            with caplog.at_level(logging.INFO, logger="test_email"):
                watch(config, logger)

    assert not pdf.exists()
    assert any((email_dir / "SENT").glob("test.*.pdf"))
    assert any(r.levelno == logging.INFO for r in caplog.records)


def test_smtp_auth_failure_leaves_file(inbox, logger, caplog):
    """An SMTPAuthenticationError leaves the file in the inbox and logs ERROR."""
    config, email_dir = inbox
    pdf = _place_pdf(email_dir)

    mock_smtp = MagicMock()
    mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp.__exit__ = MagicMock(return_value=False)
    mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad credentials")

    with patch("dispatch.email_watcher.smtplib.SMTP", return_value=mock_smtp):
        with patch("dispatch.email_watcher.fcntl.flock"):
            with caplog.at_level(logging.ERROR, logger="test_email"):
                watch(config, logger)

    assert pdf.exists()
    assert not (email_dir / "SENT" / "test.pdf").exists()
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_network_failure_leaves_file(inbox, logger, caplog):
    """A ConnectionRefusedError leaves the file in the inbox and logs ERROR."""
    config, email_dir = inbox
    pdf = _place_pdf(email_dir)

    with patch("dispatch.email_watcher.smtplib.SMTP", side_effect=ConnectionRefusedError):
        with patch("dispatch.email_watcher.fcntl.flock"):
            with caplog.at_level(logging.ERROR, logger="test_email"):
                watch(config, logger)

    assert pdf.exists()
    assert not (email_dir / "SENT" / "test.pdf").exists()
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_destination_already_exists(inbox, logger):
    """When SENT/test.pdf already exists, the move silently overwrites it (documents overwrite-on-collision behaviour)."""
    config, email_dir = inbox
    pdf = _place_pdf(email_dir)
    # Pre-place a file with the same name in the destination directory.
    _place_pdf(email_dir / "SENT")

    mock_smtp = MagicMock()
    with patch("dispatch.email_watcher.smtplib.SMTP", return_value=mock_smtp):
        with patch("dispatch.email_watcher.fcntl.flock"):
            watch(config, logger)

    assert not pdf.exists(), "PDF should have been moved out of the inbox"
    assert (email_dir / "SENT" / "test.pdf").exists()
