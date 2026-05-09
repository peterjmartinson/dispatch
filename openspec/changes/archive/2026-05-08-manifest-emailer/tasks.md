## 1. Configuration

- [x] 1.1 Add `manifest:` block to `config.yaml` with keys: `smtp_host`, `smtp_port`, `username`, `password`, `from_addr`, `alert_to`, `sqlite_path`
- [x] 1.2 Add `manifest:` block to `config.local.yaml` with real credentials and paths

## 2. Database Layer

- [x] 2.1 Implement `_open_db(sqlite_path)` — creates DB file and `manifest_sends` table if not present
- [x] 2.2 Implement `_last_status(conn, folder_name)` — returns most recent `status` for a folder, or `None`
- [x] 2.3 Implement `_log_attempt(conn, folder_name, status, to_addr, file_count, error_msg)` — inserts a row into `manifest_sends`

## 3. Email Construction

- [x] 3.1 Implement `_build_message(manifest, attachments, from_addr)` — builds `MIMEMultipart` with `to`, `subject`, `body` from manifest and all files attached
- [x] 3.2 Implement `_send_email(msg, manifest_cfg)` — opens SMTP connection using `manifest:` config block, sends message

## 4. Alert Helper

- [x] 4.1 Implement `_send_alert(folder_name, error_msg, manifest_cfg)` — sends a plain-text alert email to `config.manifest.alert_to` using the manifest SMTP credentials

## 5. Core Watcher Logic

- [x] 5.1 Implement `watch(config, logger)` — scans `print_dir` for subdirectories, opens DB, loops over manifest folders
- [x] 5.2 Add manifest folder detection: skip subdirs with no `manifest.yaml`
- [x] 5.3 Add manifest parsing: on `yaml.YAMLError` or missing required fields, call `_last_status`; alert if first error, log, skip folder
- [x] 5.4 Add attachment collection: glob all files in folder except `manifest.yaml`
- [x] 5.5 Add send path: call `_build_message`, `_send_email`; on success log `ok` + move folder to `PRINTED/`
- [x] 5.6 Add failure path: on SMTP exception, call `_last_status`; alert if first error, log `error`, leave folder in place

## 6. Entry Point

- [x] 6.1 Implement `main()` — loads `config.yaml`, sets up `RotatingFileHandler` logger, calls `watch()` (same pattern as other watchers)
- [x] 6.2 Create `run_manifest_watcher.sh` — shell entry point following same pattern as `run_email_watcher.sh`

## 7. Cron

- [x] 7.1 Add cron entry to run `run_manifest_watcher.sh` every 5 minutes

## 8. Tests

- [x] 8.1 Test manifest folder detection (with and without `manifest.yaml`)
- [x] 8.2 Test manifest parsing — valid, missing fields, malformed YAML
- [x] 8.3 Test attachment collection — mixed file types, manifest excluded, folder with no attachments
- [x] 8.4 Test success path — DB row inserted with `ok`, folder moved to `PRINTED/`
- [x] 8.5 Test first-failure alert — error logged, alert sent, folder stays in place
- [x] 8.6 Test repeat-failure suppression — second failure does not re-send alert
- [x] 8.7 Test `_open_db` auto-creates schema on first run
