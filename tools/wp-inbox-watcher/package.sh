#!/usr/bin/env bash
# Build the standalone WordPress Inbox Watcher archive without external dependencies.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="$REPO_DIR/dist"
mkdir -p "$OUTPUT_DIR"
python3 -m unittest discover -s "$SCRIPT_DIR/tests" -v
python3 -m py_compile "$SCRIPT_DIR/wp_inbox_watcher.py"
python3 - "$SCRIPT_DIR" "$OUTPUT_DIR" <<'PY'
from pathlib import Path
from sys import argv
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

src, outdir = map(Path, argv[1:])
archive = outdir / "wordpress-inbox-watcher-v0.2.zip"
members = [
    "run.sh", "README.md", "wp_inbox_watcher.py", ".gitignore",
    "tests/test_watcher.py", "tests/test_launcher.py",
]
with ZipFile(archive, "w") as zip_file:
    for filename in members:
        info = ZipInfo("wp-inbox-watcher/" + filename, date_time=(2026, 10, 16, 0, 0, 0))
        info.create_system = 3
        info.external_attr = (0o100755 if filename == "run.sh" else 0o100644) << 16
        info.compress_type = ZIP_DEFLATED
        zip_file.writestr(info, (src / filename).read_bytes())
print(f"Built: {archive}")
PY
