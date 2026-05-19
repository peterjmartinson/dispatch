#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

set -a; source <(sed 's/\r//' .env); set +a
source .venv/bin/activate
python -m dispatch.print_watcher
