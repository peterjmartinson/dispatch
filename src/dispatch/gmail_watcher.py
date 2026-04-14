"""Gmail IMAP watcher — polls a Gmail label mailbox and downloads attached PDFs into the print inbox."""
from __future__ import annotations

import email
import email.header
import imaplib
import logging
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from email.message import Message
from logging.handlers import RotatingFileHandler
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------


def _open_db(sqlite_path: str) -> sqlite3.Connection:
    """Open (or create) the SQLite database and ensure the schema exists."""
    db_path = Path(sqlite_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_attachments (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            mailbox          TEXT    NOT NULL,
            uid              TEXT    NOT NULL,
            attachment_index INTEGER NOT NULL,
            filename         TEXT,
            processed_at     TEXT    NOT NULL,
            UNIQUE (mailbox, uid, attachment_index)
        )
        """
    )
    conn.commit()
    return conn


def _is_processed(conn: sqlite3.Connection, mailbox: str, uid: str, index: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM processed_attachments WHERE mailbox=? AND uid=? AND attachment_index=?",
        (mailbox, uid, index),
    ).fetchone()
    return row is not None


def _mark_processed(
    conn: sqlite3.Connection,
    mailbox: str,
    uid: str,
    index: int,
    filename: str | None,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO processed_attachments
            (mailbox, uid, attachment_index, filename, processed_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (mailbox, uid, index, filename, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# MIME / attachment helpers
# ---------------------------------------------------------------------------


def _decode_header_value(raw: str | None) -> str:
    """Return a plain-text representation of an RFC 2047 encoded header value."""
    if raw is None:
        return ""
    parts = email.header.decode_header(raw)
    decoded_parts: list[str] = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded_parts.append(part)
    return "".join(decoded_parts)


def _extract_address(from_header: str) -> str:
    """Return the bare email address from a 'Name <addr>' or plain 'addr' header value."""
    from_header = _decode_header_value(from_header).strip()
    if "<" in from_header and ">" in from_header:
        start = from_header.index("<") + 1
        end = from_header.index(">")
        return from_header[start:end].strip().lower()
    return from_header.lower()


def _is_pdf_part(part: Message) -> bool:
    """Return True if *part* looks like a PDF attachment."""
    content_type = part.get_content_type().lower()
    if content_type == "application/pdf":
        return True
    filename = part.get_filename() or ""
    filename = _decode_header_value(filename)
    if filename.lower().endswith(".pdf"):
        return True
    # fall back to magic bytes
    payload = part.get_payload(decode=True)
    if isinstance(payload, bytes) and payload[:4] == b"%PDF":
        return True
    return False


def _safe_filename(uid: str, index: int, original: str | None) -> str:
    """Return a collision-safe .pdf filename that includes date/time, uid, and index.

    The output always ends with ``.pdf`` so the print watcher can pick it up.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if original:
        # strip path components to avoid path traversal
        stem = Path(original).stem
        # keep only safe characters
        safe_stem = "".join(c if c.isalnum() or c in "_-" else "_" for c in stem)
    else:
        safe_stem = "attachment"
    return f"{ts}_{uid}_{index}_{safe_stem}.pdf"


# ---------------------------------------------------------------------------
# Core watch function
# ---------------------------------------------------------------------------


def watch(config: dict, logger: logging.Logger) -> None:
    """Connect to Gmail via IMAP and download new PDF attachments into the drop directory.

    Args:
        config: Parsed config.yaml dict (must contain a ``gmail`` sub-section).
        logger: Caller-supplied logger.
    """
    gmail_cfg = config.get("gmail", {})

    if not gmail_cfg.get("enabled", True):
        logger.info("Gmail watcher is disabled in config; exiting.")
        return

    imap_host: str = gmail_cfg.get("imap_host", "imap.gmail.com")
    imap_port: int = int(gmail_cfg.get("imap_port", 993))
    username: str = gmail_cfg["username"]
    app_password: str = gmail_cfg["app_password"]
    mailbox: str = gmail_cfg.get("label_mailbox", "Dispatch/Print")
    allowed_senders: list[str] = [
        s.lower() for s in gmail_cfg.get("allowed_senders", [])
    ]
    sqlite_path: str = gmail_cfg.get("sqlite_path", "state/gmail_watcher.sqlite3")
    # drop_dir defaults to watch.print_dir if not specified
    drop_dir_str: str = gmail_cfg.get(
        "drop_dir",
        config.get("watch", {}).get("print_dir", ""),
    )
    if not drop_dir_str:
        raise ValueError("gmail.drop_dir (or watch.print_dir) must be set in config.yaml")

    drop_dir = Path(drop_dir_str)
    drop_dir.mkdir(parents=True, exist_ok=True)

    conn = _open_db(sqlite_path)

    try:
        logger.info("Connecting to %s:%d as %s", imap_host, imap_port, username)
        imap = imaplib.IMAP4_SSL(imap_host, imap_port)
        try:
            imap.login(username, app_password)
            _process_mailbox(imap, mailbox, allowed_senders, drop_dir, conn, logger)
        finally:
            try:
                imap.logout()
            except Exception:  # noqa: BLE001
                pass
    except imaplib.IMAP4.error as exc:
        logger.error("IMAP error: %s", exc)
    finally:
        conn.close()


def _process_mailbox(
    imap: imaplib.IMAP4_SSL,
    mailbox: str,
    allowed_senders: list[str],
    drop_dir: Path,
    conn: sqlite3.Connection,
    logger: logging.Logger,
) -> None:
    """SELECT the mailbox and iterate over all messages."""
    status, data = imap.select(f'"{mailbox}"', readonly=True)
    if status != "OK":
        logger.error("Could not SELECT mailbox %r: %s", mailbox, data)
        return

    status, data = imap.uid("SEARCH", None, "ALL")
    if status != "OK":
        logger.error("SEARCH failed for mailbox %r: %s", mailbox, data)
        return

    uid_list: list[str] = []
    if data and data[0]:
        uid_list = data[0].decode().split()

    if not uid_list:
        logger.info("No messages found in mailbox %r", mailbox)
        return

    logger.info("Found %d message(s) in %r; checking for new PDF attachments", len(uid_list), mailbox)

    for uid in uid_list:
        _process_message(imap, mailbox, uid, allowed_senders, drop_dir, conn, logger)


def _process_message(
    imap: imaplib.IMAP4_SSL,
    mailbox: str,
    uid: str,
    allowed_senders: list[str],
    drop_dir: Path,
    conn: sqlite3.Connection,
    logger: logging.Logger,
) -> None:
    """Fetch and process a single message by UID."""
    status, msg_data = imap.uid("FETCH", uid, "(RFC822)")
    if status != "OK" or not msg_data or msg_data[0] is None:
        logger.warning("Could not fetch UID %s", uid)
        return

    raw_bytes: bytes
    # msg_data is a list of tuples/bytes; we want the first tuple's second element
    for item in msg_data:
        if isinstance(item, tuple):
            raw_bytes = item[1]
            break
    else:
        logger.warning("Unexpected FETCH response for UID %s", uid)
        return

    msg = email.message_from_bytes(raw_bytes)

    from_header = msg.get("From", "")
    sender = _extract_address(from_header)

    if allowed_senders and sender not in allowed_senders:
        logger.info("Skipping UID %s — sender %r not in allowed list", uid, sender)
        return

    # Walk MIME parts and collect PDF attachments
    pdf_parts: list[tuple[int, Message]] = []
    for i, part in enumerate(msg.walk()):
        if part.get_content_maintype() == "multipart":
            continue
        if _is_pdf_part(part):
            pdf_parts.append((i, part))

    if not pdf_parts:
        logger.info("UID %s from %s: no PDF attachments found", uid, sender)
        return

    for att_index, part in pdf_parts:
        if _is_processed(conn, mailbox, uid, att_index):
            logger.info(
                "UID %s attachment %d already processed; skipping",
                uid,
                att_index,
            )
            continue

        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes) or not payload:
            logger.warning("UID %s attachment %d: empty or non-bytes payload; skipping", uid, att_index)
            continue

        orig_name = _decode_header_value(part.get_filename() or "") or None
        safe_name = _safe_filename(uid, att_index, orig_name)

        # Write to a temp file first, then atomically move into drop_dir
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf", dir=drop_dir)
            try:
                os.write(tmp_fd, payload)
            finally:
                os.close(tmp_fd)
            dest = drop_dir / safe_name
            shutil.move(tmp_path, str(dest))
        except OSError as exc:
            logger.error(
                "Failed to write attachment for UID %s index %d: %s",
                uid,
                att_index,
                exc,
            )
            continue

        _mark_processed(conn, mailbox, uid, att_index, orig_name)
        logger.info(
            "OK: saved UID %s attachment %d (%s) → %s",
            uid,
            att_index,
            orig_name or "unnamed",
            dest,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    config_path = Path(__file__).resolve().parents[2] / "config.yaml"
    with open(config_path) as fh:
        config = yaml.safe_load(fh)

    log_dir = Path(__file__).resolve().parents[3] / "logfiles"
    log_dir.mkdir(exist_ok=True)

    logger = logging.getLogger("gmail_watcher")
    logger.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        log_dir / "gmail_watcher.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=7,
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))

    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(stderr_handler)

    watch(config, logger)


if __name__ == "__main__":
    main()
