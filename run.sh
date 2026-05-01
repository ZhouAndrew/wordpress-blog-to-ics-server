#!/usr/bin/env bash
set -euo pipefail
source .venv/bin/activate
python -m wp_log_parser app --config ./config.json
