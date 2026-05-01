@echo off
call .venv\Scripts\activate
python -m wp_log_parser app --config .\config.json
