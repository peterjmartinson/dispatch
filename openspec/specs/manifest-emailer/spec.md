## ADDED Requirements

### Requirement: Manifest folder detection
The system SHALL scan `print_dir` for subdirectories and treat any subdirectory containing a `manifest.yaml` file as a manifest folder eligible for processing.

#### Scenario: Folder with manifest is detected
- **WHEN** the watcher runs and `print_dir` contains a subdirectory with a `manifest.yaml`
- **THEN** the watcher reads and processes that manifest folder

#### Scenario: Folder without manifest is ignored
- **WHEN** the watcher runs and `print_dir` contains a subdirectory with no `manifest.yaml`
- **THEN** the watcher skips that subdirectory silently

#### Scenario: Loose files at top level are ignored
- **WHEN** the watcher runs and `print_dir` contains loose files (not in a subdirectory)
- **THEN** the watcher ignores those files (they are handled by `print_watcher` or `email_watcher`)

### Requirement: Manifest format
A `manifest.yaml` file SHALL contain exactly three fields: `to` (recipient email address), `subject` (email subject line), and `body` (plain-text email body). No other fields are required or processed.

#### Scenario: Valid manifest is parsed
- **WHEN** `manifest.yaml` contains valid YAML with `to`, `subject`, and `body`
- **THEN** the watcher extracts all three values successfully

#### Scenario: Malformed manifest triggers error handling
- **WHEN** `manifest.yaml` is missing, unreadable, or missing required fields
- **THEN** the watcher logs the error, triggers the first-failure alert flow, and leaves the folder in place

### Requirement: Attachment collection
The system SHALL attach every file in the manifest folder except `manifest.yaml` itself. All file types SHALL be supported. The `files:` enumeration in the manifest is not used; the folder contents are authoritative.

#### Scenario: All non-manifest files are attached
- **WHEN** a manifest folder contains `manifest.yaml`, `report.pdf`, and `photo.jpg`
- **THEN** the email is built with `report.pdf` and `photo.jpg` as attachments

#### Scenario: Folder with only manifest.yaml sends body-only email
- **WHEN** a manifest folder contains only `manifest.yaml` and no other files
- **THEN** the email is sent with no attachments

### Requirement: Email construction and sending
The system SHALL build a MIME multipart email using `manifest.to` as the recipient, `manifest.subject` as the subject, `manifest.body` as the plain-text body, and `config.manifest.from_addr` as the sender. SMTP credentials SHALL come exclusively from the `manifest:` config block.

#### Scenario: Email is sent with correct fields
- **WHEN** a valid manifest folder is processed
- **THEN** the outbound email has From=`config.manifest.from_addr`, To=`manifest.to`, Subject=`manifest.subject`, Body=`manifest.body`

#### Scenario: Manifest cannot override from_addr
- **WHEN** the manifest contains a `from` field
- **THEN** that field is ignored; `config.manifest.from_addr` is always used

### Requirement: Success handling
On successful send, the system SHALL log the attempt to the `manifest_sends` SQLite table (status=`ok`, `to_addr`, `file_count`, `attempt_at`) and move the entire manifest folder to `print_dir/PRINTED/`.

#### Scenario: Successful send moves folder
- **WHEN** SMTP send completes without error
- **THEN** the manifest folder is moved to `print_dir/PRINTED/<folder_name>` and is no longer present in `print_dir`

#### Scenario: Successful send is logged
- **WHEN** SMTP send completes without error
- **THEN** a row with `status='ok'`, the recipient address, and attachment count is inserted into `manifest_sends`

### Requirement: Failure handling and deduplication
On SMTP or pre-send failure, the system SHALL log the attempt to `manifest_sends` (status=`error`, `error_msg`), leave the folder in place for retry, and send one alert email to `config.manifest.alert_to`. Subsequent failures for the same folder SHALL NOT generate additional alert emails.

#### Scenario: First failure triggers alert
- **WHEN** processing a manifest folder fails and no prior `error` record exists for that `folder_name` in `manifest_sends`
- **THEN** an alert email is sent to `config.manifest.alert_to` and the error is logged

#### Scenario: Repeated failure suppresses alert
- **WHEN** processing a manifest folder fails and the most recent `manifest_sends` row for that `folder_name` has `status='error'`
- **THEN** no alert email is sent; the error is logged silently

#### Scenario: Failure leaves folder in place
- **WHEN** SMTP send fails for any reason
- **THEN** the manifest folder remains in `print_dir` and will be retried on the next cron run

#### Scenario: Pre-send failure (parse error) follows same alert deduplication
- **WHEN** `manifest.yaml` cannot be parsed and no prior error is logged for that folder
- **THEN** an alert is sent and the error is logged; subsequent runs do not re-alert

### Requirement: Independent configuration block
The manifest watcher SHALL use a dedicated `manifest:` block in `config.yaml` containing `smtp_host`, `smtp_port`, `username`, `password`, `from_addr`, `alert_to`, and `sqlite_path`. These SHALL be independent of the `email:` config block.

#### Scenario: Manifest watcher uses its own SMTP credentials
- **WHEN** the manifest watcher sends an email
- **THEN** it connects using `config.manifest.smtp_host`, `config.manifest.smtp_port`, `config.manifest.username`, and `config.manifest.password`

#### Scenario: from_addr comes from manifest config block
- **WHEN** an email is sent by the manifest watcher
- **THEN** the From address is `config.manifest.from_addr`, not `config.email.from_addr`

### Requirement: SQLite persistence
The system SHALL maintain a `manifest_sends` table in the configured SQLite database with columns: `id` (PK), `folder_name` (TEXT), `attempt_at` (ISO 8601 UTC), `status` (TEXT: `ok` or `error`), `to_addr` (TEXT, nullable), `file_count` (INTEGER, nullable), `error_msg` (TEXT, nullable).

#### Scenario: Database and table are auto-created
- **WHEN** the watcher runs and the configured SQLite file does not exist
- **THEN** the database file and `manifest_sends` table are created automatically

#### Scenario: Each attempt is logged as a new row
- **WHEN** the same manifest folder is processed on two separate runs (e.g., first fails, second succeeds)
- **THEN** two rows exist in `manifest_sends` for that `folder_name`

### Requirement: Shell entry point and cron integration
The system SHALL provide a `run_manifest_watcher.sh` script following the same pattern as the existing watcher scripts, and a cron entry that runs the watcher every 5 minutes.

#### Scenario: Shell script runs the watcher
- **WHEN** `run_manifest_watcher.sh` is executed
- **THEN** `manifest_watcher.main()` runs and exits cleanly

#### Scenario: Cron runs watcher every 5 minutes
- **WHEN** the crontab is configured
- **THEN** `run_manifest_watcher.sh` is invoked every 5 minutes
