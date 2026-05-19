## Why

The existing `email_watcher` sends PDFs to a single hardcoded recipient defined in `config.yaml`. There is no way to send files to different recipients, with custom subjects and bodies, without changing config. A manifest-driven emailer lets any consumer drop a folder into the existing print inbox and have it emailed to an arbitrary address with arbitrary content — no config changes required.

## What Changes

- New `manifest_watcher` module that scans `print_dir` for subdirectories containing a `manifest.yaml`
- Manifest specifies `to`, `subject`, and `body`; all other files in the folder become attachments (any file type)
- Separate SMTP credentials and `from_addr` in `config.yaml` under a new `manifest:` block (independent of `email:` block)
- SQLite database logs every send attempt (success and failure) with deduplication to prevent repeat alert emails
- On first failure for a given folder, an alert email is sent to a configurable admin address
- On success, the folder is moved to `print_dir/PRINTED/`
- New shell script `run_manifest_watcher.sh` and cron entry (every 5 minutes)

## Capabilities

### New Capabilities

- `manifest-emailer`: Watches `print_dir` for manifest folders, builds and sends multi-attachment emails per-manifest, logs all attempts to SQLite, and alerts on first failure per folder

### Modified Capabilities

<!-- none -->

## Impact

- `config.yaml` / `config.local.yaml`: new `manifest:` section with SMTP credentials, `from_addr`, `alert_to`, `sqlite_path`
- `src/dispatch/manifest_watcher.py`: new module (no changes to existing modules)
- `run_manifest_watcher.sh`: new shell entry point
- Crontab: one new entry
- `print_dir/PRINTED/`: existing directory reused for completed manifest folders
- No changes to `print_watcher.py`, `email_watcher.py`, or `gmail_watcher.py`
