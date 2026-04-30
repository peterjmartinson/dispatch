# dispatch

**dispatch** watches directories and delivers PDF files — either to a printer or via email. It does not know or care where the PDFs came from.

It is designed to work alongside [screamsheet](https://github.com/peterjmartinson/screamsheet), but will work with any system that drops PDFs into a directory.

---

## How it works

```
[screamsheet] ──generates PDFs──→ [incoming/PRINT/]  ──→  dispatch prints them
                                   [incoming/EMAIL/]  ──→  dispatch emails them

[Gmail label] ──Dispatch/Print──→  gmail_watcher.py  ──→  [incoming/PRINT/]  ──→  dispatch prints them
```

Three independent scripts poll their respective sources every 5 minutes via cron. When a PDF appears in an inbox, it gets delivered and moved to a `PRINTED/` or `SENT/` subfolder. If delivery fails, the file stays put and gets retried next poll.

The **Gmail watcher** is an optional third watcher that fetches PDF attachments from a Gmail label mailbox (`Dispatch/Print` by default) and drops them into the print inbox. Idempotency is enforced via a local SQLite database — Gmail state is never modified.

---

## Directory layout

```
dispatch/
├── config.yaml             ← placeholder config (committed); fill in locally and keep out of git
├── run_print_watcher.sh    ← cron wrapper for print delivery
├── run_email_watcher.sh    ← cron wrapper for email delivery
├── run_gmail_watcher.sh    ← cron wrapper for Gmail IMAP ingest
├── src/
│   └── dispatch/
│       ├── print_watcher.py
│       ├── email_watcher.py
│       └── gmail_watcher.py
├── tests/
├── logfiles/               ← created automatically
├── state/                  ← SQLite DB for Gmail watcher idempotency (gitignored)
└── incoming/
    ├── PRINT/              ← drop PDFs here to print
    │   └── PRINTED/        ← successfully printed files land here
    └── EMAIL/              ← drop PDFs here to email
        └── SENT/           ← successfully sent files land here
```

---

## Setup on your Linux box

### 1. Prerequisites

- Python 3.12+
- [`uv`](https://github.com/astral-sh/uv) — `curl -Ls https://astral.sh/uv/install.sh | sh`
- CUPS (for printing) — `sudo apt install cups`
- A printer configured and visible to `lp`

Verify your printer works before wiring up dispatch:
```bash
echo "test" | lp
```

### 2. Clone the repo

```bash
cd ~
git clone https://github.com/peterjmartinson/dispatch.git
cd dispatch
```

### 3. Install dependencies

```bash
uv sync
```

### 4. Configure

`config.yaml` is already in the repo with `${VARIABLE}` placeholders. For local use, copy it and fill in your values:

```bash
cp config.yaml config.local.yaml
# edit config.local.yaml with your real paths and credentials
```

Or edit `config.yaml` directly on your server (it is gitignored when filled in):

```yaml
watch:
  print_dir: "/home/you/dispatch/incoming/PRINT"
  email_dir: "/home/you/dispatch/incoming/EMAIL"

email:
  smtp_host: smtp.gmail.com
  smtp_port: 587
  username: you@gmail.com
  password: your_app_password   # Gmail App Password, not your real password
  from_addr: you@gmail.com
  to_addr: you@wherever.com
  subject_prefix: "Screamsheet"

gmail:
  enabled: true
  imap_host: imap.gmail.com
  imap_port: 993
  username: you@gmail.com
  app_password: "xxxx xxxx xxxx xxxx"   # Gmail App Password
  label_mailbox: "Dispatch/Print"
  allowed_senders:
    - you@gmail.com
    - familymember@gmail.com
  drop_dir: "/home/you/dispatch/incoming/PRINT"
  sqlite_path: "state/gmail_watcher.sqlite3"
```

> **Gmail App Password:** Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), create a password for "Mail", and paste it in. Do not use your real Gmail password.

### 5. Gmail setup for the Gmail watcher

1. Enable IMAP in Gmail: **Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP**.
2. Create a Gmail filter: e.g. match emails sent to `you+printthis@gmail.com` and apply label `Dispatch/Print`.
3. Ensure the label `Dispatch/Print` exists in Gmail (Gmail creates it automatically when the filter fires, but you can create it manually too).

The watcher polls that label mailbox and downloads all PDF attachments from allowed senders. Gmail state is never modified — idempotency is handled entirely via a local SQLite database at `state/gmail_watcher.sqlite3`.

### 6. Make the cron wrappers executable

```bash
chmod +x run_print_watcher.sh run_email_watcher.sh run_gmail_watcher.sh
```

### 7. Test manually

Drop a PDF into the inbox and run the watcher directly:

```bash
cp /some/file.pdf incoming/PRINT/
uv run python -m dispatch.print_watcher
```

To test the Gmail watcher:

```bash
uv run python -m dispatch.gmail_watcher
```

Check `logfiles/` to see what happened.

### 8. Wire up cron

```bash
crontab -e
```

Add:

```
# Poll PRINT inbox every 5 minutes, 6am–9am
*/5 6-9 * * * /home/you/dispatch/run_print_watcher.sh

# Poll EMAIL inbox every 5 minutes, 6am–9am
*/5 6-9 * * * /home/you/dispatch/run_email_watcher.sh

# Poll Gmail label mailbox every 5 minutes, 6am–9am
*/5 6-9 * * * /home/you/dispatch/run_gmail_watcher.sh
```

Adjust the hours to match when you want delivery. Logs go to `logfiles/` with rotation.

---

## Wiring up screamsheet

In your `screamsheet/config.yaml`, point the output directory at dispatch's inbox:

```yaml
output:
  directory: "/home/you/dispatch/incoming/PRINT"
```

When you're on the road and want email instead, change it to:

```yaml
output:
  directory: "/home/you/dispatch/incoming/EMAIL"
```

That's the only switch you need to flip. dispatch handles the rest.

---

## Logs

Each watcher writes to `logfiles/`:

```
logfiles/print_watcher.log
logfiles/email_watcher.log
logfiles/gmail_watcher.log
```

Entries look like:
```
2026-04-14 06:00:03,123 INFO: Found 2 message(s) in 'Dispatch/Print'; checking for new PDF attachments
2026-04-14 06:00:05,456 INFO: OK: saved UID 42 attachment 1 (report.pdf) → /home/you/dispatch/incoming/PRINT/20260414_060005_42_1_report.pdf
2026-04-14 06:00:05,789 INFO: UID 42 attachment 1 already processed; skipping
```

---

## Running tests

```bash
uv run pytest
```

---

## What dispatch does NOT do

- Generate PDFs
- Know what a screamsheet is
- Manage schedules (that's cron's job)
- Retry forever — if a file keeps failing, check the logs and fix the underlying issue
- Modify Gmail state (the Gmail watcher is purely read-only)

---

## Deployment Configuration

This project uses GitHub Actions for deployment. Before deploying, add the following secrets in **Settings → Secrets and variables → Actions**:

| Secret | Description |
|---|---|
| `PRINT_DIR` | Absolute path to the print watch folder on the server |
| `EMAIL_DIR` | Absolute path to the email watch folder on the server |
| `SMTP_HOST` | SMTP server hostname (e.g. `smtp.gmail.com`) |
| `SMTP_PORT` | SMTP port (e.g. `587`) |
| `EMAIL_USERNAME` | Email account username |
| `EMAIL_PASSWORD` | Email app password (not your real account password) |
| `EMAIL_FROM` | Sender email address |
| `EMAIL_TO` | Recipient email address |
| `EMAIL_SUBJECT_PREFIX` | Subject line prefix (e.g. `Screamsheet`) |
| `GMAIL_IMAP_HOST` | IMAP host (e.g. `imap.gmail.com`) |
| `GMAIL_IMAP_PORT` | IMAP port (e.g. `993`) |
| `GMAIL_USERNAME` | Gmail address to poll |
| `GMAIL_APP_PASSWORD` | Gmail App Password for IMAP access |
| `GMAIL_LABEL_MAILBOX` | Gmail label name to poll (e.g. `Dispatch/Print`) |
| `GMAIL_ALLOWED_SENDERS` | Comma-separated list of allowed sender addresses |
| `GMAIL_DROP_DIR` | Directory to drop downloaded PDFs into |
| `GMAIL_SQLITE_PATH` | Path to the SQLite state database |
| `SSH_PRIVATE_KEY` | Private SSH key for connecting to the deploy server (loaded via `webfactory/ssh-agent`) |
| `DEPLOY_HOST` | Hostname or IP of the target server |
| `DEPLOY_USER` | SSH username on the target server |
| `DEPLOY_PATH` | Absolute path on the server to deploy to |
