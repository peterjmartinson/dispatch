## ADDED Requirements

### Requirement: Poll inbox for PDF files
The print watcher SHALL scan the configured `watch.print_dir` directory for files with a `.pdf` extension each time it is invoked.

#### Scenario: PDFs detected
- **WHEN** one or more `.pdf` files are present in `watch.print_dir`
- **THEN** the watcher identifies each as a candidate for printing

#### Scenario: Non-PDF files ignored
- **WHEN** non-`.pdf` files (e.g. `.txt`, `.jpg`) are present alongside PDFs
- **THEN** the watcher does not attempt to print them

---

### Requirement: Guard against partially-written files
The print watcher SHALL attempt an exclusive non-blocking lock on each candidate file before processing it. If the lock cannot be acquired the file SHALL be skipped until the next poll.

#### Scenario: Locked file skipped
- **WHEN** a `.pdf` file is still being written (lock held by writer)
- **THEN** the watcher skips it and logs a warning

#### Scenario: Unlocked file processed
- **WHEN** a `.pdf` file is fully written and lockable
- **THEN** the watcher proceeds to print it

---

### Requirement: Submit print job via lp
The print watcher SHALL submit each ready PDF to the default printer using the `lp` command via `subprocess.run`.

#### Scenario: Successful print job
- **WHEN** `lp <filepath>` exits with return code 0
- **THEN** the watcher logs a success message and moves the file to `PRINTED/`

#### Scenario: Print failure
- **WHEN** `lp <filepath>` exits with a non-zero return code
- **THEN** the watcher logs an error and leaves the file in the inbox for the next poll

---

### Requirement: Move printed files to PRINTED subfolder
After a successful print job the watcher SHALL move the file to a `PRINTED/` subdirectory inside `watch.print_dir`.

#### Scenario: File moved after printing
- **WHEN** `lp` reports success for a file
- **THEN** the file is no longer present in `watch.print_dir` and is present in `watch.print_dir/PRINTED/`

---

### Requirement: Log all activity
The print watcher SHALL write structured log entries (timestamp, level, message) to `logfiles/print_watcher.log` using a rotating file handler, and also to stderr.

#### Scenario: Successful delivery logged
- **WHEN** a file is printed and moved
- **THEN** an INFO log entry records the filename and destination

#### Scenario: Skip logged
- **WHEN** a file is skipped due to lock
- **THEN** a WARNING log entry records the filename and reason

#### Scenario: Error logged
- **WHEN** printing fails
- **THEN** an ERROR log entry records the filename and the error detail

---

### Requirement: Settings injected at entry point
The watcher's core logic SHALL accept its configuration (watch directory, logger) as parameters, not read `config.yaml` directly. A `main()` function loads `config.yaml` and calls the core logic.

#### Scenario: Test can inject settings
- **WHEN** a unit test calls the core watcher function with a temp directory path
- **THEN** the watcher operates on that temp directory without touching the real filesystem config
