Develop a Python script (email_watcher.py) that checks a configured EMAIL inbox directory for new PDF files and sends each as an email attachment to a configured address. After sending, move the file to a SENT subfolder. Make all email credentials configurable in config.yaml. Include logging and robust error handling (SMTP failure, auth error, file not ready, etc).

- SMTP settings in config.yaml
- Support for Gmail App Passwords
- Should be startable via cron every 5 minutes
- No knowledge of content, just treats files as PDFs
