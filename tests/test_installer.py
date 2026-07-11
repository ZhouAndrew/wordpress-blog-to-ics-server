from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _write_fake_python(bin_dir: Path, *, create_config: bool, validate_fails: bool = False) -> None:
    fake = bin_dir / "python3"
    fake.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "$1 $2" == "-m venv" ]]; then
  mkdir -p "$3/bin"
  printf 'export PATH=\"%s:$PATH\"\n' "$(pwd)/fake-bin" > "$3/bin/activate"
  exit 0
fi
if [[ "$1 $2" == "-m pip" ]]; then
  exit 0
fi
if [[ "$1 $2 $3" == "-m wp_log_parser init-config" ]]; then
  {'printf \'{}\' > ./config.json' if create_config else 'true'}
  exit 0
fi
if [[ "$1 $2 $3" == "-m wp_log_parser validate-config" ]]; then
  {'exit 2' if validate_fails else 'exit 0'}
fi
echo "unexpected python invocation: $*" >&2
exit 99
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    shutil.copy(fake, bin_dir / "python")
    pip = bin_dir / "pip"
    pip.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    pip.chmod(0o755)


def _run_install(tmp_path: Path, *, create_config: bool, validate_fails: bool = False) -> subprocess.CompletedProcess[str]:
    shutil.copy(Path("install.sh"), tmp_path / "install.sh")
    (tmp_path / "requirements.txt").write_text("", encoding="utf-8")
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    _write_fake_python(bin_dir, create_config=create_config, validate_fails=validate_fails)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    return subprocess.run(
        ["bash", "install.sh"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_install_fails_when_wizard_does_not_create_config(tmp_path: Path) -> None:
    result = _run_install(tmp_path, create_config=False)

    assert result.returncode != 0
    assert "setup wizard did not create ./config.json" in result.stderr
    assert "Install complete. Run ./run.sh" not in result.stdout


def test_install_succeeds_only_after_config_exists_and_validates(tmp_path: Path) -> None:
    result = _run_install(tmp_path, create_config=True)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "config.json").exists()
    assert "Install complete. Run ./run.sh" in result.stdout


def test_install_does_not_print_success_when_validation_fails(tmp_path: Path) -> None:
    result = _run_install(tmp_path, create_config=True, validate_fails=True)

    assert result.returncode != 0
    assert "Install complete. Run ./run.sh" not in result.stdout
