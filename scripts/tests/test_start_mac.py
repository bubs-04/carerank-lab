"""Test launcher behavior with a fake Docker CLI; never starts containers."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "start_mac.sh"


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        shutil.copy2(SCRIPT, self.root / "scripts/start_mac.sh")
        fake = self.root / "bin"
        fake.mkdir()
        docker = fake / "docker"
        docker.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$CALL_LOG"
if [ "$1" = info ] && [ "${FAIL_INFO:-0}" = 1 ]; then exit 1; fi
if [ "$1 $2" = 'compose config' ] && [ "${FAIL_CONFIG:-0}" = 1 ]; then exit 1; fi
''')
        docker.chmod(0o700)
        self.env = {**os.environ, "PATH": str(fake) + os.pathsep + os.environ.get("PATH", ""),
                    "CALL_LOG": str(self.root / "calls")}

    def launch(self, **env):
        return subprocess.run(["sh", str(self.root / "scripts/start_mac.sh")],
                              env={**self.env, **env}, capture_output=True, text=True)

    def test_creates_private_configuration_and_preserves_it(self):
        self.assertEqual(self.launch().returncode, 0)
        path = self.root / ".env"
        content = path.read_text()
        self.assertRegex(content, r"^POSTGRES_PASSWORD=[a-f0-9]{48}\nAPI_DATABASE_PASSWORD=[a-f0-9]{48}\n\nWORKER_DATABASE_PASSWORD=[a-f0-9]{48}\n$")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        again = self.launch()
        self.assertEqual(again.returncode, 0)
        self.assertEqual(path.read_text(), content)
        self.assertNotIn(content.split("=")[1].strip(), again.stdout)

    def test_upgrade_preserves_owner_password_and_adds_separate_runtime_secret(self):
        path = self.root / ".env"
        path.write_text("POSTGRES_PASSWORD=existing-secret\nAPP_ENV=development\n")
        self.assertEqual(self.launch().returncode, 0)
        content = path.read_text()
        self.assertIn("POSTGRES_PASSWORD=existing-secret\nAPP_ENV=development\n", content)
        self.assertRegex(content, r"API_DATABASE_PASSWORD=[a-f0-9]{48}\n\nWORKER_DATABASE_PASSWORD=[a-f0-9]{48}\n$")
        self.assertEqual(content.count("API_DATABASE_PASSWORD="), 1)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_unavailable_engine_does_not_create_configuration(self):
        self.assertNotEqual(self.launch(FAIL_INFO="1").returncode, 0)
        self.assertFalse((self.root / ".env").exists())
        self.assertNotIn("compose up", (self.root / "calls").read_text())

    def test_bad_configuration_does_not_start_services(self):
        self.assertNotEqual(self.launch(FAIL_CONFIG="1").returncode, 0)
        self.assertNotIn("compose up", (self.root / "calls").read_text())


if __name__ == "__main__":
    unittest.main()
