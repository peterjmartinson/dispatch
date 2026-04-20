# dispatch

**dispatch** watches directories and delivers PDF files — either to a printer or via email. It does not know or care where the PDFs came from.

It is designed to work alongside [screamsheet](https://github.com/peterjmartinson/screamsheet), but will work with any system that drops PDFs into a directory.

---

## How it works

```
[screamsheet] ──generates PDFs──→ [incoming/PRINT/]  ──→  dispatch prints them
                                   [incoming/EMAIL/]  ──→  dispatch emails them
```

Two independent scripts poll their respective inboxes every 5 minutes via cron. When a PDF appears, it gets delivered and moved to a `PRINTED/` or `SENT/` subfolder. If delivery fails, the file stays put and gets retried next poll.

---

## Directory layout

```
dispatch/
├── config.yaml             ← placeholder config (committed); filled in at deploy time
├── run_print_watcher.sh    ← cron wrapper for print delivery
├── run_email_watcher.sh    ← cron wrapper for email delivery
├── src/
│   └── dispatch/
│       ├── print_watcher.py
│       └── email_watcher.py
├── tests/
├── logfiles/               ← created automatically
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
```

> **Gmail App Password:** Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), create a password for "Mail", and paste it in. Do not use your real Gmail password.

### 5. Make the cron wrappers executable

```bash
chmod +x run_print_watcher.sh run_email_watcher.sh
```

### 6. Test manually

Drop a PDF into the inbox and run the watcher directly:

```bash
cp /some/file.pdf incoming/PRINT/
uv run python -m paperboy.print_watcher
```

Check `logfiles/` to see what happened.

### 7. Wire up cron

```bash
crontab -e
```

Add:

```
# Poll PRINT inbox every 5 minutes, 6am–9am
*/5 6-9 * * * /home/you/dispatch/run_print_watcher.sh

# Poll EMAIL inbox every 5 minutes, 6am–9am
*/5 6-9 * * * /home/you/dispatch/run_email_watcher.sh
```

Adjust the hours to match when you want delivery. Logs go to `logfiles/` with one file per day.

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

Each watcher writes a daily log to `logfiles/`:

```
logfiles/print_watcher_20260410.log
logfiles/email_watcher_20260410.log
```

Entries look like:
```
[06:00:03] INFO: Found 5 PDF(s).
[06:00:05] INFO: OK: MLB_gamescores_20260410.pdf sent to printer.
[06:00:05] INFO: Archived: MLB_gamescores_20260410.pdf → incoming/PRINT/PRINTED/MLB_gamescores_20260410.pdf
[06:00:07] ERROR: FAILED: lp exited 1 for NHL_gamescores_20260410.pdf.
[06:00:07] WARNING: Will retry NHL_gamescores_20260410.pdf next poll.
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
| `SSH_PRIVATE_KEY` | Private SSH key for connecting to the deploy server |
| `DEPLOY_HOST` | Hostname or IP of the target server |
| `DEPLOY_USER` | SSH username on the target server |
| `DEPLOY_PATH` | Absolute path on the server to deploy to |
