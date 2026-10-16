"""Simulate missing Tkinter without installing any actual OS package."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


RUN_SH = Path(__file__).resolve().parents[1] / "run.sh"


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.fakebin = root / "bin"
        self.fakebin.mkdir()
        self.installed = root / "installed"
        self.called = root / "apt-called"
        self._exe("python3", """#!/bin/bash
if [[ $1 == -c ]]; then
  [[ -f "$MOCK_TK_INSTALLED" ]]
  exit $?
fi
printf 'FAKE_APP: %s\\n' "$*"
""")
        self._exe("apt-get", """#!/bin/bash
printf '%s\\n' "$*" > "$MOCK_APT_CALLED"
touch "$MOCK_TK_INSTALLED"
""")
        self._exe("zenity", "#!/bin/bash\nexit 0\n")
        # GitHub runners are non-root: intercept PolicyKit instead of invoking it.
        self._exe("pkexec", '#!/bin/bash\nexec "$@"\n')
        self.env = dict(os.environ, PATH=f"{self.fakebin}:{os.environ['PATH']}",
                        MOCK_TK_INSTALLED=str(self.installed),
                        MOCK_APT_CALLED=str(self.called), DISPLAY=":7")

    def _exe(self, name, body):
        target = self.fakebin / name
        target.write_text(body)
        target.chmod(0o755)

    def run_launcher(self, *args):
        return subprocess.run(["bash", str(RUN_SH), *args], env=self.env,
                              capture_output=True, text=True, timeout=10)

    def test_gui_installs_missing_tk_then_launches(self):
        run = self.run_launcher("/tmp/fake-inbox")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.called.read_text().strip(), "install -y python3-tk")
        self.assertIn("FAKE_APP:", run.stdout)
        self.assertIn("/tmp/fake-inbox", run.stdout)

    def test_no_gui_does_not_install_tk(self):
        run = self.run_launcher("--no-gui", "/tmp/fake-inbox")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(self.called.exists())
        self.assertIn("--no-gui", run.stdout)

    def test_help_does_not_install_tk(self):
        run = self.run_launcher("--help")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(self.called.exists())

    def test_declined_install_does_not_launch(self):
        self._exe("zenity", "#!/bin/bash\nexit 1\n")
        run = self.run_launcher("/tmp/fake-inbox")
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse(self.called.exists())
        self.assertNotIn("FAKE_APP:", run.stdout)


if __name__ == "__main__":
    unittest.main()
