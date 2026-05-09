"""Tests for dispatch.manifest_watcher."""
import logging
import smtplib
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import yaml

from dispatch.manifest_watcher import (
    _last_status,
    _log_attempt,
    _open_db,
    watch,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def print_dir(tmp_path):
    d = tmp_path / "PRINT"
    d.mkdir()
    (d / "PRINTED").mkdir()
    return d


@pytest.fixture()
def config(tmp_path, print_dir):
    db = tmp_path / "manifest_watcher.sqlite3"
    return {
        "watch": {"print_dir": str(print_dir)},
        "manifest": {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "username": "sender@example.com",
            "password": "secret",
            "from_addr": "sender@example.com",
            "alert_to": "admin@example.com",
            "sqlite_path": str(db),
        },
    }


@pytest.fixture()
def logger():
    return logging.getLogger("test_manifest")


def _make_folder(print_dir: Path, name: str, manifest: dict, extra_files: list[str] | None = None) -> Path:
    """Create a manifest folder with the given manifest content and optional extra files."""
    folder = print_dir / name
    folder.mkdir()
    (folder / "manifest.yaml").write_text(yaml.dump(manifest))
    for fname in (extra_files or []):
        (folder / fname).write_bytes(b"fake content")
    return folder


# ---------------------------------------------------------------------------
# 8.7 _open_db auto-creates schema
# ---------------------------------------------------------------------------


def test_open_db_creates_schema(tmp_path):
    """_open_db creates the DB file and manifest_sends table on first run."""
    db_path = tmp_path / "subdir" / "manifest_watcher.sqlite3"
    assert not db_path.exists()

    conn = _open_db(str(db_path))

    assert db_path.exists()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='manifest_sends'"
    ).fetchone()
    assert row is not None, "manifest_sends table was not created"
    conn.close()


# ---------------------------------------------------------------------------
# 8.1 Manifest folder detection
# ---------------------------------------------------------------------------


def test_folder_with_manifest_is_processed(print_dir, config, logger):
    """A subfolder containing manifest.yaml is processed."""
    folder = _make_folder(print_dir, "job-001", {"to": "a@b.com", "subject": "Hi", "body": "Test"})

    mock_smtp = MagicMock()
    with patch("dispatch.manifest_watcher.smtplib.SMTP", return_value=mock_smtp):
        watch(config, logger)

    assert not folder.exists(), "Folder should be moved to PRINTED on success"
    assert (print_dir / "PRINTED" / "job-001").exists()


def test_folder_without_manifest_is_ignored(print_dir, config, logger):
    """A subfolder with no manifest.yaml is silently skipped."""
    folder = print_dir / "no-manifest"
    folder.mkdir()
    (folder / "somefile.pdf").write_bytes(b"data")

    with patch("dispatch.manifest_watcher.smtplib.SMTP") as mock_smtp_cls:
        watch(config, logger)

    mock_smtp_cls.assert_not_called()
    assert folder.exists(), "Folder without manifest should stay in place"


def test_empty_print_dir_is_fine(print_dir, config, logger):
    """watch() handles an empty print_dir without error."""
    with patch("dispatch.manifest_watcher.smtplib.SMTP") as mock_smtp_cls:
        watch(config, logger)

    mock_smtp_cls.assert_not_called()


# ---------------------------------------------------------------------------
# 8.2 Manifest parsing
# ---------------------------------------------------------------------------


def test_valid_manifest_is_parsed(print_dir, config, logger):
    """A well-formed manifest results in an email sent with correct fields."""
    _make_folder(print_dir, "job-002", {"to": "dest@example.com", "subject": "Subj", "body": "Body"})

    mock_smtp = MagicMock()
    with patch("dispatch.manifest_watcher.smtplib.SMTP", return_value=mock_smtp):
        watch(config, logger)

    mock_smtp.__enter__.return_value.sendmail.assert_called_once()
    args = mock_smtp.__enter__.return_value.sendmail.call_args
    assert args[0][1] == "dest@example.com"


def test_missing_field_triggers_error(print_dir, config, logger):
    """A manifest missing required fields leaves the folder in place and logs an error."""
    folder = print_dir / "bad-manifest"
    folder.mkdir()
    (folder / "manifest.yaml").write_text(yaml.dump({"to": "x@y.com"}))  # missing subject & body

    with patch("dispatch.manifest_watcher.smtplib.SMTP") as mock_smtp_cls:
        with patch("dispatch.manifest_watcher._send_alert") as mock_alert:
            watch(config, logger)

    mock_smtp_cls.assert_not_called()
    mock_alert.assert_called_once()
    assert folder.exists(), "Folder with bad manifest should stay in place"


def test_malformed_yaml_triggers_error(print_dir, config, logger):
    """A manifest with invalid YAML leaves the folder in place and sends an alert."""
    folder = print_dir / "malformed"
    folder.mkdir()
    (folder / "manifest.yaml").write_text("to: [\nbad yaml")

    with patch("dispatch.manifest_watcher.smtplib.SMTP") as mock_smtp_cls:
        with patch("dispatch.manifest_watcher._send_alert") as mock_alert:
            watch(config, logger)

    mock_smtp_cls.assert_not_called()
    mock_alert.assert_called_once()
    assert folder.exists()


# ---------------------------------------------------------------------------
# 8.3 Attachment collection
# ---------------------------------------------------------------------------


def test_all_non_manifest_files_attached(print_dir, config, logger):
    """All files except manifest.yaml are attached to the email."""
    _make_folder(
        print_dir, "job-003",
        {"to": "r@r.com", "subject": "S", "body": "B"},
        extra_files=["report.pdf", "photo.jpg", "data.csv"],
    )

    sent_messages = []

    def capture_send(from_addr, to_addr, msg_string):
        sent_messages.append(msg_string)

    mock_smtp_instance = MagicMock()
    mock_smtp_instance.__enter__ = lambda s: mock_smtp_instance
    mock_smtp_instance.__exit__ = MagicMock(return_value=False)
    mock_smtp_instance.sendmail.side_effect = capture_send

    with patch("dispatch.manifest_watcher.smtplib.SMTP", return_value=mock_smtp_instance):
        watch(config, logger)

    assert len(sent_messages) == 1
    msg_str = sent_messages[0]
    assert "report.pdf" in msg_str
    assert "photo.jpg" in msg_str
    assert "data.csv" in msg_str
    assert "manifest.yaml" not in msg_str


def test_folder_with_no_attachments_sends_email(print_dir, config, logger):
    """A manifest folder with no extra files sends an email with no attachments."""
    _make_folder(print_dir, "job-nofiles", {"to": "r@r.com", "subject": "S", "body": "B"})

    mock_smtp = MagicMock()
    with patch("dispatch.manifest_watcher.smtplib.SMTP", return_value=mock_smtp):
        watch(config, logger)

    mock_smtp.__enter__.return_value.sendmail.assert_called_once()


# ---------------------------------------------------------------------------
# 8.4 Success path
# ---------------------------------------------------------------------------


def test_success_logs_ok_to_db(print_dir, config, logger):
    """A successful send inserts a row with status='ok' into manifest_sends."""
    _make_folder(
        print_dir, "job-004",
        {"to": "r@r.com", "subject": "S", "body": "B"},
        extra_files=["a.pdf", "b.pdf"],
    )

    mock_smtp = MagicMock()
    with patch("dispatch.manifest_watcher.smtplib.SMTP", return_value=mock_smtp):
        watch(config, logger)

    conn = sqlite3.connect(config["manifest"]["sqlite_path"])
    row = conn.execute(
        "SELECT status, to_addr, file_count FROM manifest_sends WHERE folder_name='job-004'"
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "ok"
    assert row[1] == "r@r.com"
    assert row[2] == 2


def test_success_moves_folder_to_printed(print_dir, config, logger):
    """A successful send moves the entire folder to PRINTED/."""
    folder = _make_folder(print_dir, "job-005", {"to": "r@r.com", "subject": "S", "body": "B"})

    mock_smtp = MagicMock()
    with patch("dispatch.manifest_watcher.smtplib.SMTP", return_value=mock_smtp):
        watch(config, logger)

    assert not folder.exists()
    assert (print_dir / "PRINTED" / "job-005").exists()


# ---------------------------------------------------------------------------
# 8.5 First-failure alert
# ---------------------------------------------------------------------------


def test_first_smtp_failure_logs_and_alerts(print_dir, config, logger):
    """First SMTP failure logs an error row and sends one alert."""
    folder = _make_folder(print_dir, "job-006", {"to": "r@r.com", "subject": "S", "body": "B"})

    with patch("dispatch.manifest_watcher.smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.return_value.__enter__.return_value.sendmail.side_effect = (
            smtplib.SMTPException("connection refused")
        )
        with patch("dispatch.manifest_watcher._send_alert") as mock_alert:
            watch(config, logger)

    mock_alert.assert_called_once()
    assert folder.exists(), "Folder should stay in place after failure"

    conn = sqlite3.connect(config["manifest"]["sqlite_path"])
    row = conn.execute(
        "SELECT status FROM manifest_sends WHERE folder_name='job-006'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "error"


# ---------------------------------------------------------------------------
# 8.6 Repeat-failure suppression
# ---------------------------------------------------------------------------


def test_repeated_failure_does_not_re_alert(print_dir, config, logger):
    """If the last DB record is already 'error', no additional alert is sent."""
    folder = _make_folder(print_dir, "job-007", {"to": "r@r.com", "subject": "S", "body": "B"})

    # Pre-seed an existing error record
    conn = _open_db(config["manifest"]["sqlite_path"])
    _log_attempt(conn, "job-007", "error", error_msg="prior failure")
    conn.close()

    with patch("dispatch.manifest_watcher.smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.return_value.__enter__.return_value.sendmail.side_effect = (
            smtplib.SMTPException("still broken")
        )
        with patch("dispatch.manifest_watcher._send_alert") as mock_alert:
            watch(config, logger)

    mock_alert.assert_not_called()
    assert folder.exists()
