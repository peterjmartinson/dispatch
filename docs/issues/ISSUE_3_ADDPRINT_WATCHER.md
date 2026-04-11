Create a standalone Python script (print_watcher.py) that polls a configured PRINT inbox directory and sends any found PDF files to the default printer. After printing, move each file to a PRINTED subfolder. Include logging of all activities and error handling for common issues (printer offline, file still being written, etc).

- Uses config.yaml for the target PRINT directory
- Provides clear logs in a logfiles/ folder
- Should be easily startable via cronjob every 5 minutes
- No knowledge of where PDFs were generated
