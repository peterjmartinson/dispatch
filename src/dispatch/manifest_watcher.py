"""Manifest watcher — polls email_dir for manifest folders and sends each as a multi-attachment email."""
from __future__ import annotations

import logging
import os
import shutil
import smtplib
import sqlite3
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from logging.handlers import RotatingFileHandler
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _open_db(sqlite_path: str) -> sqlite3.Connection:
    """Open (or create) the SQLite database and ensure the manifest_sends table exists."""
    db_path = Path(sqlite_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS manifest_sends (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_name  TEXT    NOT NULL,
            attempt_at   TEXT    NOT NULL,
            status       TEXT    NOT NULL,
            to_addr      TEXT,
            file_count   INTEGER,
            error_msg    TEXT
        )
        """
    )
    conn.commit()
    return conn


def _last_status(conn: sqlite3.Connection, folder_name: str) -> str | None:
    """Return the most recent status ('ok' or 'error') for *folder_name*, or None."""
    row = conn.execute(
        "SELECT status FROM manifest_sends WHERE folder_name=? ORDER BY attempt_at DESC LIMIT 1",
        (folder_name,),
    ).fetchone()
    return row[0] if row else None


def _log_attempt(
    conn: sqlite3.Connection,
    folder_name: str,
    status: str,
    to_addr: str | None = None,
    file_count: int | None = None,
    error_msg: str | None = None,
) -> None:
    """Insert a row into manifest_sends."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO manifest_sends (folder_name, attempt_at, status, to_addr, file_count, error_msg)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (folder_name, now, status, to_addr, file_count, error_msg),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------------


def _build_message(manifest: dict, attachments: list[Path], from_addr: str) -> MIMEMultipart:
    """Build a MIMEMultipart email from manifest fields with all files attached."""
    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = manifest["to"]
    msg["Subject"] = manifest["subject"]
    msg.attach(MIMEText(manifest["body"], "plain"))
    for path in attachments:
        with open(path, "rb") as fh:
            part = MIMEApplication(fh.read(), Name=path.name)
        part["Content-Disposition"] = f'attachment; filename="{path.name}"'
        msg.attach(part)
    return msg


def _send_email(msg: MIMEMultipart, manifest_cfg: dict) -> None:
    """Send *msg* via SMTP using credentials from the manifest config block."""
    with smtplib.SMTP(manifest_cfg["smtp_host"], manifest_cfg["smtp_port"]) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(manifest_cfg["username"], manifest_cfg["password"])
        smtp.sendmail(manifest_cfg["from_addr"], msg["To"], msg.as_string())


# ---------------------------------------------------------------------------
# Alert helper
# ---------------------------------------------------------------------------


def _send_alert(folder_name: str, error_msg: str, manifest_cfg: dict) -> None:
    """Send a one-time plain-text alert to alert_to when a manifest folder first fails."""
    msg = MIMEMultipart()
    msg["From"] = manifest_cfg["from_addr"]
    msg["To"] = manifest_cfg["alert_to"]
    msg["Subject"] = f"DISPATCH ALERT: manifest folder '{folder_name}' failed"
    body = (
        f"Manifest folder '{folder_name}' failed to send.\n\n"
        f"Error: {error_msg}\n\n"
        "The folder has been left in place for retry.\n"
        "Check the manifest_watcher log for details."
    )
    msg.attach(MIMEText(body, "plain"))
    try:
        with smtplib.SMTP(manifest_cfg["smtp_host"], manifest_cfg["smtp_port"]) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(manifest_cfg["username"], manifest_cfg["password"])
            smtp.sendmail(manifest_cfg["from_addr"], manifest_cfg["alert_to"], msg.as_string())
    except Exception:
        pass  # Alert failure must not mask the original error; already logged to DB


# ---------------------------------------------------------------------------
# Core watcher
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = {"to", "subject", "body"}


def watch(config: dict, logger: logging.Logger) -> None:
    """Scan email_dir for manifest folders and send each as a multi-attachment email."""
    email_dir = Path(config["watch"]["email_dir"])
    sent_dir = email_dir / "SENT"
    sent_dir.mkdir(parents=True, exist_ok=True)

    manifest_cfg = config["manifest"]
    conn = _open_db(manifest_cfg["sqlite_path"])

    subdirs = sorted(p for p in email_dir.iterdir() if p.is_dir() and p.name != "SENT")
    if not subdirs:
        logger.info("No subdirectories found in %s", email_dir)
        return

    for folder in subdirs:
        folder_name = folder.name
        manifest_path = folder / "manifest.yaml"

        # --- Detection ---
        if not manifest_path.exists():
            logger.debug("Skipping %s — no manifest.yaml", folder_name)
            continue

        # --- Parsing ---
        try:
            with open(manifest_path) as fh:
                manifest = yaml.safe_load(fh)
            if not manifest or not _REQUIRED_FIELDS.issubset(manifest.keys()):
                missing = _REQUIRED_FIELDS - set(manifest.keys() if manifest else [])
                raise ValueError(f"manifest.yaml missing required fields: {missing}")
        except (yaml.YAMLError, ValueError, OSError) as exc:
            err = str(exc)
            logger.error("Manifest parse error in %s: %s", folder_name, err)
            if _last_status(conn, folder_name) != "error":
                _log_attempt(conn, folder_name, "error", error_msg=err)
                _send_alert(folder_name, err, manifest_cfg)
            continue

        # --- Attachment collection ---
        attachments = sorted(
            p for p in folder.iterdir()
            if p.is_file()
            and p.name != "manifest.yaml"
            and "zone.identifier" not in p.name.lower()
        )
        logger.info(
            "Processing %s → %s (%d attachment(s))", folder_name, manifest["to"], len(attachments)
        )

        # --- Send ---
        try:
            msg = _build_message(manifest, attachments, manifest_cfg["from_addr"])
            _send_email(msg, manifest_cfg)
        except (smtplib.SMTPException, OSError) as exc:
            err = str(exc)
            logger.error("Send failed for %s: %s", folder_name, err)
            if _last_status(conn, folder_name) != "error":
                _log_attempt(conn, folder_name, "error", error_msg=err)
                _send_alert(folder_name, err, manifest_cfg)
            continue

        # --- Success ---
        _log_attempt(conn, folder_name, "ok", to_addr=manifest["to"], file_count=len(attachments))
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        dest = sent_dir / f"{folder_name}.{ts}"
        shutil.move(str(folder), str(dest))
        logger.info("OK: %s sent to %s → %s", folder_name, manifest["to"], dest)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    config_path = Path(__file__).resolve().parents[2] / "config.yaml"
    with open(config_path) as fh:
        config = yaml.safe_load(os.path.expandvars(fh.read()))

    log_dir = Path(__file__).resolve().parents[3] / "logfiles"
    log_dir.mkdir(exist_ok=True)

    logger = logging.getLogger("manifest_watcher")
    logger.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        log_dir / "manifest_watcher.log",
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
