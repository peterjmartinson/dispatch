"""Print watcher — polls an inbox directory for PDF files and sends each to the default printer."""
from __future__ import annotations

import fcntl
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import yaml


def watch(config: dict, logger: logging.Logger) -> None:
    """Scan the configured PRINT inbox and send any PDF files to the default printer.

    Args:
        config: Parsed config.yaml dict (must contain ``config["watch"]["print_dir"]``).
        logger: Caller-supplied logger — makes the function easy to test.
    """
    print_dir = Path(config["watch"]["print_dir"])
    printed_dir = print_dir / "PRINTED"
    printed_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(print_dir.glob("*.pdf"))
    if not pdfs:
        logger.info("No PDF files found in %s", print_dir)
        return

    logger.info("Found %d PDF(s) in %s", len(pdfs), print_dir)

    for pdf in pdfs:
        if not _try_lock(pdf, logger):
            continue
        _submit(pdf, printed_dir, logger)


def _try_lock(path: Path, logger: logging.Logger) -> bool:
    """Return True if an exclusive non-blocking lock on *path* can be acquired."""
    try:
        with open(path, "rb") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.warning("Skipping %s — file is locked (still being written)", path.name)
        return False
    return True


def _submit(pdf: Path, printed_dir: Path, logger: logging.Logger) -> None:
    """Send *pdf* to the default printer via ``lp``; move it to *printed_dir* on success."""
    result = subprocess.run(["lp", str(pdf)], capture_output=True)
    if result.returncode == 0:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        dest = printed_dir / f"{pdf.stem}.{ts}{pdf.suffix}"
        shutil.move(str(pdf), dest)
        logger.info("OK: %s sent to printer → %s", pdf.name, dest)
    else:
        stderr = result.stderr.decode(errors="replace").strip()
        logger.error("FAILED: lp exited %d for %s. stderr: %s", result.returncode, pdf.name, stderr)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    config_path = Path(__file__).resolve().parents[2] / "config.yaml"
    with open(config_path) as fh:
        config = yaml.safe_load(os.path.expandvars(fh.read()))

    log_dir = Path(__file__).resolve().parents[3] / "logfiles"
    log_dir.mkdir(exist_ok=True)

    logger = logging.getLogger("print_watcher")
    logger.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        log_dir / "print_watcher.log",
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
