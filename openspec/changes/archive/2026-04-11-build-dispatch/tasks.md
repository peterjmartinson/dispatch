## 1. Project Skeleton

- [x] 1.1 Create `incoming/PRINT/PRINTED/` and `incoming/EMAIL/SENT/` directories with `.gitkeep` files
- [x] 1.2 Create `logfiles/` directory with `.gitkeep` and add `logfiles/*.log` to `.gitignore`
- [x] 1.3 Create `config.yaml.example` with all required keys (`watch.print_dir`, `watch.email_dir`, and all `email.*` settings)
- [x] 1.4 Add `config.yaml` to `.gitignore`
- [x] 1.5 Create `src/dispatch/__init__.py` (empty) to make `dispatch` a package
- [x] 1.6 Create `run_print_watcher.sh` cron wrapper that activates the `uv` venv and runs `print_watcher.main()`
- [x] 1.7 Create `run_email_watcher.sh` cron wrapper that activates the `uv` venv and runs `email_watcher.main()`
- [x] 1.8 Add pytest and any test dependencies to `pyproject.toml` / `uv` extras; verify `uv sync` succeeds
- [x] 1.9 Update README with a "Running tests" section (`pytest` command)

## 2. Test Suite (TDD — write before implementations)

- [x] 2.1 Create `tests/__init__.py` (empty)
- [x] 2.2 Create `tests/test_print_watcher.py` with a fixture that builds a temp inbox + `PRINTED/` directory
- [x] 2.3 Write test: `test_pdf_detected` — asserts a `.pdf` in the temp inbox is included in the watcher's candidate list
- [x] 2.4 Write test: `test_non_pdf_ignored` — asserts a `.txt` file is not included in the candidate list
- [x] 2.5 Write test: `test_locked_file_skipped` — mocks `fcntl.flock` to raise `BlockingIOError`; asserts `subprocess.run` is not called and a WARNING is logged
- [x] 2.6 Write test: `test_successful_print_moves_file` — mocks `subprocess.run` with `returncode=0`; asserts file lands in `PRINTED/` and INFO is logged
- [x] 2.7 Write test: `test_failed_print_leaves_file` — mocks `subprocess.run` with `returncode=1`; asserts file remains in inbox and ERROR is logged
- [x] 2.8 Create `tests/test_email_watcher.py` with a fixture that builds a temp inbox + `SENT/` directory and a mock SMTP settings dict
- [x] 2.9 Write test: `test_pdf_detected` — asserts a `.pdf` in the temp inbox is included in the candidate list
- [x] 2.10 Write test: `test_non_pdf_ignored` — asserts non-PDF files are excluded
- [x] 2.11 Write test: `test_locked_file_skipped` — mocks `fcntl.flock` to raise `BlockingIOError`; asserts SMTP send is not called and WARNING is logged
- [x] 2.12 Write test: `test_successful_send_moves_file` — mock SMTP send passes; asserts file lands in `SENT/` and INFO is logged
- [x] 2.13 Write test: `test_smtp_auth_failure_leaves_file` — mock SMTP raises `SMTPAuthenticationError`; asserts file stays in inbox and ERROR is logged
- [x] 2.14 Write test: `test_network_failure_leaves_file` — mock SMTP raises `ConnectionRefusedError`; asserts file stays in inbox and ERROR is logged
- [x] 2.15 Run `pytest tests/` and confirm all tests **fail** (import errors expected — implementations not written yet)

## 3. Print Watcher Implementation

- [x] 3.1 Create `src/dispatch/print_watcher.py` with a `watch(config: dict, logger: logging.Logger) -> None` function
- [x] 3.2 Implement PDF scanning: list all `.pdf` files in `config["watch"]["print_dir"]`
- [x] 3.3 Implement file-lock guard using `fcntl.flock(LOCK_EX | LOCK_NB)`; log WARNING and skip on `BlockingIOError`
- [x] 3.4 Implement `lp` submission via `subprocess.run(["lp", filepath], capture_output=True)`
- [x] 3.5 On `returncode == 0`: move file to `PRINTED/` subfolder; log INFO
- [x] 3.6 On non-zero returncode: log ERROR with stderr output; leave file in inbox
- [x] 3.7 Implement `main()`: load `config.yaml`, set up rotating file + stderr logger, call `watch()`
- [x] 3.8 Ensure `logfiles/` is created automatically if absent
- [x] 3.9 Run `pytest tests/test_print_watcher.py` — all tests must pass

## 4. Email Watcher Implementation

- [x] 4.1 Create `src/dispatch/email_watcher.py` with a `watch(config: dict, logger: logging.Logger, smtp_factory=None) -> None` function
- [x] 4.2 Implement PDF scanning: list all `.pdf` files in `config["watch"]["email_dir"]`
- [x] 4.3 Implement file-lock guard (same pattern as print watcher)
- [x] 4.4 Implement SMTP send: open STARTTLS connection, login, build `MIMEMultipart` message with PDF attachment, send
- [x] 4.5 Subject line: `f"{config['email']['subject_prefix']}: {filename}"`
- [x] 4.6 On success: move file to `SENT/` subfolder; log INFO
- [x] 4.7 On `SMTPAuthenticationError`: log ERROR; leave file in inbox
- [x] 4.8 On `ConnectionRefusedError` or other `SMTPException`: log ERROR; leave file in inbox
- [x] 4.9 Implement `main()`: load `config.yaml`, set up rotating file + stderr logger, call `watch()`
- [x] 4.10 Run `pytest tests/test_email_watcher.py` — all tests must pass

## 5. Final Verification

- [x] 5.1 Run the full test suite `pytest` and confirm zero failures
- [x] 5.2 Verify `config.yaml` is listed in `.gitignore` and not staged
- [x] 5.3 Manually test print watcher end-to-end: drop a PDF in `incoming/PRINT/`, run `run_print_watcher.sh`, confirm it lands in `PRINTED/` and log entry is written
- [x] 5.4 Manually test email watcher end-to-end: drop a PDF in `incoming/EMAIL/`, run `run_email_watcher.sh`, confirm it lands in `SENT/` and the email is received
