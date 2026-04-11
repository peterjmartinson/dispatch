## ADDED Requirements

### Requirement: Test suite uses pytest
The project SHALL include a `tests/` directory with pytest-compatible test files for both watchers.

#### Scenario: Tests discoverable by pytest
- **WHEN** `pytest` is run from the project root
- **THEN** all test files in `tests/` are discovered and executed without configuration errors

---

### Requirement: Print watcher tests cover core scenarios
The test suite SHALL include tests for `print_watcher` that exercise: PDF detection, file locking/skip, successful print + move, and print failure + file retained.

#### Scenario: New PDF is detected and queued
- **WHEN** a `.pdf` file is placed in the temp inbox directory
- **THEN** the watcher includes it in the list of files to process

#### Scenario: Locked PDF is skipped
- **WHEN** a `.pdf` file has an exclusive lock held by another process
- **THEN** `subprocess.run` is NOT called for that file and a warning is logged

#### Scenario: Successful print moves file to PRINTED
- **WHEN** the mocked `subprocess.run` returns returncode 0
- **THEN** the file is moved to the `PRINTED/` subfolder and an INFO log entry is recorded

#### Scenario: Print failure leaves file in inbox
- **WHEN** the mocked `subprocess.run` returns a non-zero returncode
- **THEN** the file remains in the inbox and an ERROR log entry is recorded

---

### Requirement: Email watcher tests cover core scenarios
The test suite SHALL include tests for `email_watcher` that exercise: PDF detection, file locking/skip, successful send + move, SMTP auth failure, and network failure.

#### Scenario: New PDF is detected and queued
- **WHEN** a `.pdf` file is placed in the temp inbox directory
- **THEN** the watcher includes it in the list of files to process

#### Scenario: Locked PDF is skipped
- **WHEN** a `.pdf` file has an exclusive lock held by another process
- **THEN** the mock SMTP send is NOT called for that file and a warning is logged

#### Scenario: Successful send moves file to SENT
- **WHEN** the mock SMTP transport accepts the message without raising
- **THEN** the file is moved to the `SENT/` subfolder and an INFO log entry is recorded

#### Scenario: SMTP auth failure leaves file in inbox
- **WHEN** the mock SMTP raises `smtplib.SMTPAuthenticationError`
- **THEN** the file remains in the inbox and an ERROR log entry is recorded

#### Scenario: Network failure leaves file in inbox
- **WHEN** the mock SMTP raises `ConnectionRefusedError`
- **THEN** the file remains in the inbox and an ERROR log entry is recorded

---

### Requirement: External dependencies are mocked
All tests SHALL mock `subprocess.run` (for `lp`) and the SMTP transport so no real printer or mail server is required to run the suite.

#### Scenario: Tests pass without CUPS installed
- **WHEN** CUPS is not installed on the test machine
- **THEN** the print watcher tests still pass because `subprocess.run` is mocked

#### Scenario: Tests pass without network access
- **WHEN** there is no network access or SMTP server available
- **THEN** the email watcher tests still pass because the SMTP transport is mocked

---

### Requirement: Tests written before implementations (TDD)
The test files SHALL be committed and the tests confirmed failing **before** the watcher implementation files are written.

#### Scenario: Tests fail before implementation
- **WHEN** test files exist but `print_watcher.py` and `email_watcher.py` do not
- **THEN** `pytest` reports import errors or assertion failures, not passing tests

#### Scenario: Tests pass after implementation
- **WHEN** both watcher implementation files satisfy the specs
- **THEN** `pytest` reports all tests passing with zero failures
