"""Email watcher — polls an inbox directory for PDF files and sends each as an email attachment."""
from __future__ import annotations

import fcntl
import logging
import os
import shutil
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from logging.handlers import RotatingFileHandler
from pathlib import Path

import yaml


def watch(config: dict, logger: logging.Logger) -> None:
    """Scan the configured EMAIL inbox and send any PDF files as email attachments.

    Args:
        config: Parsed config.yaml dict (must contain ``config["watch"]["email_dir"]``
                and all ``config["email"]`` sub-keys).
        logger: Caller-supplied logger — makes the function easy to test.
    """
    email_dir = Path(config["watch"]["email_dir"])
    sent_dir = email_dir / "SENT"
    sent_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(email_dir.glob("*.pdf"))
    if not pdfs:
        logger.info("No PDF files found in %s", email_dir)
        return

    logger.info("Found %d PDF(s) in %s", len(pdfs), email_dir)

    for pdf in pdfs:
        if not _try_lock(pdf, logger):
            continue
        _send(pdf, sent_dir, config["email"], logger)


def _try_lock(path: Path, logger: logging.Logger) -> bool:
    """Return True if an exclusive non-blocking lock on *path* can be acquired."""
    try:
        with open(path, "rb") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.warning("Skipping %s — file is locked (still being written)", path.name)
        return False
    return True


def _build_message(pdf: Path, email_cfg: dict) -> MIMEMultipart:
    """Construct a MIMEMultipart email with the PDF attached."""
    msg = MIMEMultipart()
    msg["From"] = email_cfg["from_addr"]
    msg["To"] = email_cfg["to_addr"]
    msg["Subject"] = f"{email_cfg['subject_prefix']}: {pdf.name}"
    msg.attach(MIMEText("Please find the attached PDF.", "plain"))

    with open(pdf, "rb") as fh:
        part = MIMEApplication(fh.read(), Name=pdf.name)
    part["Content-Disposition"] = f'attachment; filename="{pdf.name}"'
    msg.attach(part)
    return msg


def _send(pdf: Path, sent_dir: Path, email_cfg: dict, logger: logging.Logger) -> None:
    """Send *pdf* via SMTP and move it to *sent_dir* on success."""
    try:
        with smtplib.SMTP(email_cfg["smtp_host"], email_cfg["smtp_port"]) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(email_cfg["username"], email_cfg["password"])
            msg = _build_message(pdf, email_cfg)
            smtp.sendmail(email_cfg["from_addr"], email_cfg["to_addr"], msg.as_string())

        dest = sent_dir / pdf.name
        shutil.move(str(pdf), dest)
        logger.info("OK: %s sent to %s → %s", pdf.name, email_cfg["to_addr"], dest)

    except smtplib.SMTPAuthenticationError as exc:
        logger.error("FAILED (auth): %s — %s", pdf.name, exc)
    except (ConnectionRefusedError, smtplib.SMTPException) as exc:
        logger.error("FAILED (smtp): %s — %s", pdf.name, exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    config_path = Path(__file__).resolve().parents[2] / "config.yaml"
    with open(config_path) as fh:
        config = yaml.safe_load(os.path.expandvars(fh.read()))

    log_dir = Path(__file__).resolve().parents[3] / "logfiles"
    log_dir.mkdir(exist_ok=True)

    logger = logging.getLogger("email_watcher")
    logger.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        log_dir / "email_watcher.log",
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
