## ADDED Requirements

### Requirement: Inbox directories exist
The repository SHALL contain the directory structure `incoming/PRINT/PRINTED/` and `incoming/EMAIL/SENT/` so watchers have a ready-made inbox and success folder on first clone.

#### Scenario: PRINT inbox present
- **WHEN** the repository is cloned fresh
- **THEN** `incoming/PRINT/` directory exists and is tracked by git (via `.gitkeep`)

#### Scenario: PRINTED subfolder present
- **WHEN** the repository is cloned fresh
- **THEN** `incoming/PRINT/PRINTED/` directory exists and is tracked by git (via `.gitkeep`)

#### Scenario: EMAIL inbox present
- **WHEN** the repository is cloned fresh
- **THEN** `incoming/EMAIL/` directory exists and is tracked by git (via `.gitkeep`)

#### Scenario: SENT subfolder present
- **WHEN** the repository is cloned fresh
- **THEN** `incoming/EMAIL/SENT/` directory exists and is tracked by git (via `.gitkeep`)

---

### Requirement: Example config provided
The repository SHALL include `config.yaml.example` with all required keys so a new user can copy it to `config.yaml` and fill in their values.

#### Scenario: All required keys present
- **WHEN** a developer opens `config.yaml.example`
- **THEN** it contains `watch.print_dir`, `watch.email_dir`, `email.smtp_host`, `email.smtp_port`, `email.username`, `email.password`, `email.from_addr`, `email.to_addr`, and `email.subject_prefix`

#### Scenario: Real config gitignored
- **WHEN** `config.yaml` is created locally
- **THEN** `.gitignore` prevents it from being committed to the repository

---

### Requirement: Cron wrapper scripts provided
The repository SHALL include `run_print_watcher.sh` and `run_email_watcher.sh` that activate the virtual environment and invoke the appropriate watcher, suitable for use in a crontab.

#### Scenario: Print wrapper is executable
- **WHEN** the repository is cloned and `chmod +x run_print_watcher.sh` is run
- **THEN** the script can be invoked directly without `bash` prefix

#### Scenario: Email wrapper is executable
- **WHEN** the repository is cloned and `chmod +x run_email_watcher.sh` is run
- **THEN** the script can be invoked directly without `bash` prefix

---

### Requirement: Logfiles directory created at runtime
The system SHALL create the `logfiles/` directory automatically on first run if it does not exist.

#### Scenario: Directory auto-created
- **WHEN** a watcher starts and `logfiles/` does not exist
- **THEN** the directory is created before any log entries are written
