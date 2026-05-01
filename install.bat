@echo off
python -m venv .venv
call .venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements.txt
if not exist output mkdir output
if not exist errors mkdir errors
if not exist logs mkdir logs
if not exist config.json (
  python -m wp_log_parser init-config --wizard --config .\config.json
)
echo Install complete. Run run.bat
