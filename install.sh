#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt
mkdir -p output errors logs
if [ ! -f config.json ]; then
  python -m wp_log_parser init-config --wizard --config ./config.json
fi
echo "Install complete. Run ./run.sh"
