"""Tests for dispatch.gmail_watcher — no real IMAP connection required."""
from __future__ import annotations

import email
import email.mime.application
import email.mime.multipart
import email.mime.text
import logging
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dispatch.gmail_watcher import watch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_msg(
    from_addr: str,
    attachments: list[tuple[str, bytes]],
    include_text: bool = True,
) -> bytes:
    """Build a minimal RFC 822 message with optional PDF attachments.

    Args:
        from_addr: The From header value.
        attachments: List of (filename, content) tuples to attach.
        include_text: Whether to include a plain-text body part.
    """
    msg = email.mime.multipart.MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = "recipient@example.com"
    msg["Subject"] = "Test"

    if include_text:
        msg.attach(email.mime.text.MIMEText("hello", "plain"))

    for filename, content in attachments:
        part = email.mime.application.MIMEApplication(content, Name=filename)
        part["Content-Disposition"] = f'attachment; filename="{filename}"'
        msg.attach(part)

    return msg.as_bytes()


def _make_pdf_bytes() -> bytes:
    return b"%PDF-1.4 fake pdf content"


def _make_fake_imap(uid_list: list[str], messages: dict[str, bytes]) -> MagicMock:
    """Return a fake IMAP4_SSL instance.

    Args:
        uid_list: The UIDs returned by SEARCH ALL.
        messages: Mapping of uid → raw RFC 822 bytes.
    """
    imap = MagicMock()
    imap.__enter__ = MagicMock(return_value=imap)
    imap.__exit__ = MagicMock(return_value=False)

    # SELECT returns OK
    imap.select.return_value = ("OK", [b"1"])

    # SEARCH returns the uid list
    uid_bytes = b" ".join(u.encode() for u in uid_list)
    imap.uid = MagicMock()

    def fake_uid(command, *args):
        if command == "SEARCH":
            return ("OK", [uid_bytes])
        if command == "FETCH":
            uid = args[0]
            raw = messages.get(uid, b"")
            return ("OK", [(b"1 (RFC822 {%d})" % len(raw), raw)])
        return ("NO", [b"unknown"])

    imap.uid.side_effect = fake_uid
    imap.logout.return_value = ("BYE", [b""])
    return imap


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def drop_dir(tmp_path):
    d = tmp_path / "PRINT"
    d.mkdir()
    return d


@pytest.fixture()
def sqlite_path(tmp_path):
    return str(tmp_path / "state" / "gmail_watcher.sqlite3")


@pytest.fixture()
def logger():
    return logging.getLogger("test_gmail")


def _config(drop_dir: Path, sqlite_path: str) -> dict:
    return {
        "watch": {"print_dir": str(drop_dir)},
        "gmail": {
            "enabled": True,
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
            "username": "user@gmail.com",
            "app_password": "secret",
            "label_mailbox": "Dispatch/Print",
            "allowed_senders": [
                "peter.j.martinson@gmail.com",
                "annashavin@gmail.com",
            ],
            "sqlite_path": sqlite_path,
            "drop_dir": str(drop_dir),
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_allowed_sender_multiple_pdfs(drop_dir, sqlite_path, logger):
    """An allowed sender with 2 PDF attachments: both files are saved and both DB rows recorded."""
    pdf1 = _make_pdf_bytes()
    pdf2 = b"%PDF-1.5 another fake pdf"
    raw_msg = _make_msg(
        "peter.j.martinson@gmail.com",
        [("report1.pdf", pdf1), ("report2.pdf", pdf2)],
    )

    fake_imap = _make_fake_imap(["1"], {"1": raw_msg})
    config = _config(drop_dir, sqlite_path)

    with patch("dispatch.gmail_watcher.imaplib.IMAP4_SSL", return_value=fake_imap):
        watch(config, logger)

    pdfs = list(drop_dir.glob("*.pdf"))
    assert len(pdfs) == 2, f"Expected 2 PDFs, got {len(pdfs)}: {pdfs}"

    # Check DB rows
    conn = sqlite3.connect(sqlite_path)
    rows = conn.execute("SELECT uid, attachment_index FROM processed_attachments ORDER BY attachment_index").fetchall()
    conn.close()
    assert len(rows) == 2
    # Indices reflect walk() position: 0=multipart, 1=text/plain, 2=first pdf, 3=second pdf
    assert rows[0][0] == "1"  # uid
    assert rows[1][0] == "1"  # uid
    assert rows[0][1] < rows[1][1]  # indices are ordered


def test_disallowed_sender_skipped(drop_dir, sqlite_path, logger, caplog):
    """An email from a sender not in the allowlist is skipped — no files, no DB rows."""
    raw_msg = _make_msg("spammer@evil.com", [("malware.pdf", _make_pdf_bytes())])
    fake_imap = _make_fake_imap(["2"], {"2": raw_msg})
    config = _config(drop_dir, sqlite_path)

    with patch("dispatch.gmail_watcher.imaplib.IMAP4_SSL", return_value=fake_imap):
        with caplog.at_level(logging.INFO, logger="test_gmail"):
            watch(config, logger)

    assert list(drop_dir.glob("*.pdf")) == [], "No PDFs should be saved for disallowed sender"

    conn = sqlite3.connect(sqlite_path)
    rows = conn.execute("SELECT COUNT(*) FROM processed_attachments").fetchone()
    conn.close()
    assert rows[0] == 0


def test_rerun_idempotency(drop_dir, sqlite_path, logger):
    """Running watch twice with the same messages does not create duplicate files or DB rows."""
    raw_msg = _make_msg("annashavin@gmail.com", [("doc.pdf", _make_pdf_bytes())])
    fake_imap1 = _make_fake_imap(["3"], {"3": raw_msg})
    fake_imap2 = _make_fake_imap(["3"], {"3": raw_msg})
    config = _config(drop_dir, sqlite_path)

    with patch("dispatch.gmail_watcher.imaplib.IMAP4_SSL", return_value=fake_imap1):
        watch(config, logger)

    with patch("dispatch.gmail_watcher.imaplib.IMAP4_SSL", return_value=fake_imap2):
        watch(config, logger)

    pdfs = list(drop_dir.glob("*.pdf"))
    assert len(pdfs) == 1, f"Expected exactly 1 PDF after two runs, got {len(pdfs)}"

    conn = sqlite3.connect(sqlite_path)
    rows = conn.execute("SELECT COUNT(*) FROM processed_attachments").fetchone()
    conn.close()
    assert rows[0] == 1, "DB should have exactly 1 row after two identical runs"


def test_non_pdf_attachment_ignored(drop_dir, sqlite_path, logger):
    """A non-PDF attachment is silently ignored; no file is dropped."""
    # Build a message with a .txt attachment (no PDF)
    msg = email.mime.multipart.MIMEMultipart()
    msg["From"] = "peter.j.martinson@gmail.com"
    msg["To"] = "someone@example.com"
    msg["Subject"] = "No PDFs here"
    msg.attach(email.mime.text.MIMEText("body", "plain"))
    txt_part = email.mime.application.MIMEApplication(b"plain text data", Name="notes.txt")
    txt_part["Content-Disposition"] = 'attachment; filename="notes.txt"'
    msg.attach(txt_part)
    raw_msg = msg.as_bytes()

    fake_imap = _make_fake_imap(["4"], {"4": raw_msg})
    config = _config(drop_dir, sqlite_path)

    with patch("dispatch.gmail_watcher.imaplib.IMAP4_SSL", return_value=fake_imap):
        watch(config, logger)

    assert list(drop_dir.glob("*.pdf")) == [], "Non-PDF attachment should not be saved"


def test_pdf_detected_by_magic_bytes(drop_dir, sqlite_path, logger):
    """An attachment without a .pdf filename but with PDF magic bytes is still saved."""
    # Craft a part with content-type application/octet-stream, no .pdf extension,
    # but %PDF- magic bytes
    msg = email.mime.multipart.MIMEMultipart()
    msg["From"] = "peter.j.martinson@gmail.com"
    msg["To"] = "someone@example.com"
    msg["Subject"] = "Hidden PDF"
    msg.attach(email.mime.text.MIMEText("body", "plain"))
    part = email.mime.application.MIMEApplication(b"%PDF-1.4 hidden content", Name="document.bin")
    part["Content-Disposition"] = 'attachment; filename="document.bin"'
    msg.attach(part)
    raw_msg = msg.as_bytes()

    fake_imap = _make_fake_imap(["5"], {"5": raw_msg})
    config = _config(drop_dir, sqlite_path)

    with patch("dispatch.gmail_watcher.imaplib.IMAP4_SSL", return_value=fake_imap):
        watch(config, logger)

    pdfs = list(drop_dir.glob("*.pdf"))
    assert len(pdfs) == 1, "PDF detected by magic bytes should be saved"


def test_disabled_watcher_exits_early(drop_dir, sqlite_path, logger, caplog):
    """When gmail.enabled is False, the watcher exits without connecting."""
    raw_msg = _make_msg("peter.j.martinson@gmail.com", [("report.pdf", _make_pdf_bytes())])
    fake_imap = _make_fake_imap(["6"], {"6": raw_msg})
    config = _config(drop_dir, sqlite_path)
    config["gmail"]["enabled"] = False

    with patch("dispatch.gmail_watcher.imaplib.IMAP4_SSL", return_value=fake_imap) as mock_cls:
        with caplog.at_level(logging.INFO, logger="test_gmail"):
            watch(config, logger)

    mock_cls.assert_not_called()
    assert list(drop_dir.glob("*.pdf")) == []


def test_name_angle_bracket_sender_parsed(drop_dir, sqlite_path, logger):
    """A From header with 'Name <addr>' format is parsed correctly for allowlist check."""
    raw_msg = _make_msg(
        "Peter Martinson <peter.j.martinson@gmail.com>",
        [("invoice.pdf", _make_pdf_bytes())],
    )
    fake_imap = _make_fake_imap(["7"], {"7": raw_msg})
    config = _config(drop_dir, sqlite_path)

    with patch("dispatch.gmail_watcher.imaplib.IMAP4_SSL", return_value=fake_imap):
        watch(config, logger)

    pdfs = list(drop_dir.glob("*.pdf"))
    assert len(pdfs) == 1, "Sender with Name <addr> form should be accepted"
