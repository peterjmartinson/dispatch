## Context

Dispatch is a small Python cron-driven system with three independent watchers: `print_watcher` (loose PDFs → physical printer), `email_watcher` (loose PDFs → single hardcoded email), and `gmail_watcher` (IMAP → drops PDFs into print inbox). All share a single `config.yaml` and a common pattern: a `watch(config, logger)` function with a standalone `main()` entry point.

The `print_watcher` scans `print_dir` for `*.pdf` files at the top level only — it never descends into subdirectories. This makes the same directory safe to use for manifest folders without any collision.

## Goals / Non-Goals

**Goals:**
- Add a fourth watcher that processes manifest folders (subdirectories of `print_dir` containing `manifest.yaml`)
- Send multi-attachment emails with per-manifest recipient, subject, and body
- Use independent SMTP credentials and `from_addr` (separate from the `email:` config block)
- Log every send attempt to SQLite; send one alert email on first failure per folder — never spam
- Move completed folders to `print_dir/PRINTED/` on success; leave failed folders in place for retry

**Non-Goals:**
- Scheduled/timed sending (dropped = send on next run)
- Modifying `print_watcher`, `email_watcher`, or `gmail_watcher`
- Supporting nested subdirectories inside a manifest folder
- Validating or restricting attachment file types

## Decisions

**Single directory, two watcher types distinguished by shape (file vs. folder)**
The `print_watcher` only globs `*.pdf` at the top level so subdirectories are invisible to it. No dedicated `manifest_dir` needed. Simpler drop zone, fewer paths to manage.
_Alternative considered_: dedicated `manifest_dir` — rejected, adds config complexity and a second folder for users to remember.

**No scheduling in manifest**
Dropped = sent on next cron run. A scheduling field creates backlog risk (missed window = stuck folder) and complicates the state machine with no clear benefit for this use case.
_Alternative considered_: `scheduled_at` with a 5-minute tolerance window — rejected by user during design.

**Deduplication via SQLite, not a sentinel file**
The DB already exists for `gmail_watcher`. Storing attempt history enables alerting logic (has this folder already been alerted?) without cluttering the filesystem with marker files.
`folder_name` (the subdirectory name) is the stable key. On each run: query the most recent row for that folder; if it's already `error`, skip the alert.
_Alternative considered_: write a `.error` sentinel file into the folder — rejected, mixes state into the data directory.

**Separate SQLite database file**
`manifest_watcher` gets its own `sqlite_path` (e.g. `manifest_watcher.sqlite3`) rather than sharing `gmail_watcher.sqlite3`. Keeps schemas independent and failure domains isolated.

**Separate `manifest:` config block with own SMTP credentials**
The `email:` block sends from a Gmail address. The manifest emailer needs to send from `peter@distractedfortune.com` via a different SMTP provider. Sharing would require multiplexing credentials in the same block, which is fragile.

**Attach all files except `manifest.yaml`**
No `files:` list in the manifest. The folder IS the attachment list. Eliminates a class of user error (manifest lists a file that isn't there, or a file exists that isn't listed).

## Risks / Trade-offs

**Folder renamed between runs** → The `folder_name` key in the DB becomes stale; the next run treats it as a new folder and may re-alert or re-attempt. Mitigation: document that folder names should not be changed after dropping.

**SMTP failure after `sendmail()` but before `shutil.move()`** → Email was delivered but folder stays in `print_dir`. On next run, a second send attempt occurs. Mitigation: acceptable given low-frequency cron; documenting this edge case is sufficient. A future enhancement could write a `.sent` marker before the move.

**Large attachments** → All files are loaded into memory before sending. For typical dispatch use (documents, invoices) this is fine. No mitigation needed unless file sizes grow to hundreds of MB.

**Alert email uses same SMTP credentials as sends** → If SMTP is broken, the alert also fails silently. Mitigation: logged to DB regardless; user can check DB or log file.

## Migration Plan

1. Add `manifest:` block to `config.yaml` (template) and `config.local.yaml` (real credentials)
2. Deploy `src/dispatch/manifest_watcher.py`
3. Deploy `run_manifest_watcher.sh`
4. Add cron entry
5. No rollback risk — all existing watchers unchanged; new module is purely additive
