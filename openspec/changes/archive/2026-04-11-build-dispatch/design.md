## Context

`dispatch` is a greenfield project. Nothing exists yet except the README and issue descriptions. The goal is to implement the full system in one change: directory skeleton, two watcher scripts, and a pytest suite written TDD-style (tests first, implementations second).

Each watcher runs on a 5-minute cron. It scans an inbox directory, delivers every PDF it finds, then moves each file to a success subfolder. Delivery is idempotent: if the cron fires while a previous run is still active there is no overlap problem because cron simply skips overlapping runs (or the run completes quickly before the next tick).

Runtime configuration (directories, SMTP credentials) is loaded from `config.yaml` at startup. For testability, both watchers accept their settings as injected arguments so unit tests never touch the real filesystem or live services.

## Goals / Non-Goals

**Goals:**
- Complete project skeleton with cron wrappers and example config
- `print_watcher.py` that delivers PDFs via `lp` and moves them to `PRINTED/`
- `email_watcher.py` that delivers PDFs as SMTP attachments and moves them to `SENT/`
- Pytest suite written **before** the implementations (TDD): tests define the contract, implementations satisfy them
- Settings injected as parameters so tests use temp directories and mock transports

**Non-Goals:**
- PDF generation (delegated to screamsheet or any other tool)
- GUI or web interface
- Deduplication beyond "file is no longer in inbox after delivery"
- Retry scheduling / dead-letter queue (failed files simply stay in the inbox for the next poll)
- Support for non-PDF file types

## Decisions

### 1. Settings injection over global config reads

**Decision**: Each watcher exposes a callable entry-point that accepts a settings dict (or dataclass) rather than reading `config.yaml` itself. The cron wrapper calls a thin `main()` that loads the YAML and calls the entry-point.

**Rationale**: Makes unit testing trivial — pass a dict with a temp dir path and a mock transport, no patching of file-system globals needed.

**Alternative considered**: Patch `open` / `yaml.safe_load` in tests. Rejected because it couples tests tightly to implementation internals.

---

### 2. TDD ordering: tests before implementations

**Decision**: The task sequence is: skeleton → failing tests → print_watcher implementation → email_watcher implementation.

**Rationale**: Aligns with the explicit project requirement (ISSUE_5 precedes ISSUE_3/4 in intent). Tests serve as the living specification; the watcher implementations are judged correct when tests pass.

---

### 3. `lp` command for printing

**Decision**: Use `subprocess.run(["lp", filepath])` to submit print jobs. No CUPS Python binding.

**Rationale**: `lp` is universally available wherever CUPS is installed; avoids an extra dependency. Easier to mock in tests (`unittest.mock.patch("subprocess.run")`).

---

### 4. `smtplib` for email

**Decision**: Use the standard-library `smtplib` + `email` packages. No third-party mail library.

**Rationale**: Zero additional dependencies; sufficient for the use case of attaching a single PDF and sending via SMTP with STARTTLS.

---

### 5. File-locking guard

**Decision**: Before processing a PDF, check it is not still being written by attempting to open it exclusively (`fcntl.flock` with `LOCK_EX | LOCK_NB`). Skip the file if it is locked; it will be picked up on the next poll.

**Rationale**: Prevents reading a partially-written file from screamsheet or any other producer. Straightforward to test with mocks.

---

### 6. Log to rotating file + stderr

**Decision**: Each watcher configures Python's `logging` with a `RotatingFileHandler` targeting `logfiles/<watcher>.log` and a `StreamHandler` to stderr.

**Rationale**: cron captures stderr to the user's mailbox by default, giving free alerting on failures. The rotating file keeps disk usage bounded.

## Risks / Trade-offs

- **CUPS not installed on test machine** → `lp` calls are mocked in tests so CI does not require CUPS.
- **SMTP credentials in config.yaml** → File is gitignored; only `config.yaml.example` committed. Warning in README.
- **cron overlap if delivery hangs** → Standard cron has no lock; if a watcher takes > 5 minutes a second instance starts. Mitigation: the `PRINTED/`/`SENT/` move is the last step, so a re-run simply skips already-delivered files (they are gone from the inbox).
- **No retry backoff** → Files that fail delivery stay in the inbox and are retried every 5 minutes indefinitely. Acceptable for a lightweight local tool; could cause log spam if a printer is offline for hours.
