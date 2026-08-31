#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f .env ]; then
  set -a; source <(sed 's/\r//' .env); set +a
fi
source .venv/bin/activate
python -m dispatch.print_watcher
