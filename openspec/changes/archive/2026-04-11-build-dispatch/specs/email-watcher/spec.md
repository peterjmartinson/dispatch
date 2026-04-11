## ADDED Requirements

### Requirement: Poll inbox for PDF files
The email watcher SHALL scan the configured `watch.email_dir` directory for files with a `.pdf` extension each time it is invoked.

#### Scenario: PDFs detected
- **WHEN** one or more `.pdf` files are present in `watch.email_dir`
- **THEN** the watcher identifies each as a candidate for emailing

#### Scenario: Non-PDF files ignored
- **WHEN** non-`.pdf` files are present alongside PDFs
- **THEN** the watcher does not attempt to email them

---

### Requirement: Guard against partially-written files
The email watcher SHALL attempt an exclusive non-blocking lock on each candidate file before processing it. If the lock cannot be acquired the file SHALL be skipped until the next poll.

#### Scenario: Locked file skipped
- **WHEN** a `.pdf` file is still being written
- **THEN** the watcher skips it and logs a warning

#### Scenario: Unlocked file processed
- **WHEN** a `.pdf` file is fully written and lockable
- **THEN** the watcher proceeds to email it

---

### Requirement: Send PDF as email attachment via SMTP
The email watcher SHALL connect to the configured SMTP server using STARTTLS, authenticate with the supplied credentials, and send a message with the PDF attached.

#### Scenario: Successful send
- **WHEN** the SMTP server accepts the message
- **THEN** the watcher logs success and moves the file to `SENT/`

#### Scenario: SMTP authentication failure
- **WHEN** the server rejects the credentials
- **THEN** the watcher logs an ERROR and leaves the file in the inbox

#### Scenario: Network/SMTP failure
- **WHEN** the SMTP connection cannot be established or drops mid-send
- **THEN** the watcher logs an ERROR and leaves the file in the inbox

---

### Requirement: Subject line uses configured prefix
The email subject SHALL be `<subject_prefix>: <filename>` where `subject_prefix` comes from `config.yaml`.

#### Scenario: Subject formatted correctly
- **WHEN** `subject_prefix` is `"Screamsheet"` and the file is `report.pdf`
- **THEN** the email subject is `"Screamsheet: report.pdf"`

---

### Requirement: Move sent files to SENT subfolder
After a successful send the watcher SHALL move the file to a `SENT/` subdirectory inside `watch.email_dir`.

#### Scenario: File moved after sending
- **WHEN** the SMTP server confirms delivery
- **THEN** the file is no longer present in `watch.email_dir` and is present in `watch.email_dir/SENT/`

---

### Requirement: Log all activity
The email watcher SHALL write structured log entries to `logfiles/email_watcher.log` using a rotating file handler, and also to stderr.

#### Scenario: Successful delivery logged
- **WHEN** a file is sent and moved
- **THEN** an INFO log entry records the filename, recipient, and destination

#### Scenario: Skip logged
- **WHEN** a file is skipped due to lock
- **THEN** a WARNING log entry records the filename and reason

#### Scenario: Error logged
- **WHEN** sending fails
- **THEN** an ERROR log entry records the filename and the error detail

---

### Requirement: Settings injected at entry point
The watcher's core logic SHALL accept its configuration (watch directory, SMTP settings, logger) as parameters. A `main()` function loads `config.yaml` and calls the core logic.

#### Scenario: Test can inject settings
- **WHEN** a unit test calls the core watcher function with a temp directory and a mock SMTP transport
- **THEN** no real SMTP connection is made and no real filesystem config is read
