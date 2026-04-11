## Why

The dispatch project needs a complete implementation — project skeleton, both watcher scripts, and a test suite — to deliver PDF files reliably to a printer or email recipient. The building blocks are defined in the issue tracker but have not yet been written.

## What Changes

- Add project skeleton: directory layout (`incoming/PRINT/`, `incoming/EMAIL/`, `logfiles/`), `config.yaml.example`, and cron wrapper scripts
- Add `src/dispatch/print_watcher.py`: polls `incoming/PRINT/` and sends PDFs to the default printer via `lp`, then moves them to `PRINTED/`
- Add `src/dispatch/email_watcher.py`: polls `incoming/EMAIL/` and sends PDFs as email attachments, then moves them to `SENT/`
- Add `tests/` with pytest unit tests written **before** the watcher implementations (TDD)
- Settings are injected as constructor arguments / function parameters so tests never touch the filesystem or live services

## Capabilities

### New Capabilities

- `project-skeleton`: Repository directory structure, example config, cron wrappers, and README setup instructions
- `print-watcher`: Poll a configured directory for PDF files and send each to the default printer; move delivered files to `PRINTED/`; log all activity
- `email-watcher`: Poll a configured directory for PDF files and send each as an email attachment via SMTP; move delivered files to `SENT/`; log all activity
- `watcher-tests`: Pytest suite covering both watchers — file discovery, successful delivery, failure/retry behaviour, file-locking edge cases, and logging output using mocked `lp` and SMTP

### Modified Capabilities

<!-- none -->

## Impact

- **New files**: `config.yaml.example`, `run_print_watcher.sh`, `run_email_watcher.sh`, `src/dispatch/print_watcher.py`, `src/dispatch/email_watcher.py`, `tests/test_print_watcher.py`, `tests/test_email_watcher.py`
- **Dependencies**: Python 3.12+, `uv`, CUPS (`lp` command), standard-library `smtplib`/`email`; `pytest` for tests
- **External systems**: Default CUPS printer, Gmail (or any SMTP server) via App Password credentials in `config.yaml`
- **No breaking changes** to existing interfaces (project is greenfield)
