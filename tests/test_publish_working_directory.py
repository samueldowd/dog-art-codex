"""A safe cwd repairs dedicated-user spawn without relaxing home permissions."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def test_activation_and_services_choose_application_owned_working_directory():
    template = (ROOT / "scripts/activate-live.template.sh").read_text()
    assert template.index("cd /") < template.index(
        '/bin/sh "$protected/scripts/install-release.sh"'
    )
    installer = (ROOT / "scripts/install-release.sh").read_text()
    assert installer.index("cd /") < installer.index("runuser -u dog-art")
    for name in ("dog-art.service", "dog-art-reset.service"):
        assert "WorkingDirectory=/var/lib/dog-art" in (ROOT / "deploy/systemd" / name).read_text()


@pytest.mark.skipif(os.getuid() == 0, reason="root can traverse mode000 directories")
def test_real_spawn_failure_from_private_cwd_and_recovery_from_safe_cwd(tmp_path):
    import sys

    script = tmp_path / "spawn_probe.py"
    blocked = tmp_path / "private-home"
    safe = tmp_path / "safe-app"
    blocked.mkdir()
    safe.mkdir()
    script.write_text("""
import os,sys
from dog_art.publishing.transport_process import BoundedSMBTransport
class FakeTransport:
 def read(self,path):return b'ok'
 def close(self):pass
def factory(settings):return FakeTransport()
if __name__=='__main__':
 blocked,safe,mode=sys.argv[1:]
 os.chdir(blocked);os.chmod(blocked,0)
 try:
  if mode=='safe':os.chdir(safe)
  adapter=BoundedSMBTransport(None,timeout=5,factory=factory)
  try:assert adapter.read('owned')==b'ok'
  finally:adapter.close()
  print('spawn_success')
 except Exception as error:
  print('spawn_failed:'+type(error).__name__)
 finally:os.chmod(blocked,0o700)
""")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    for mode, expected in [("blocked", "spawn_failed"), ("safe", "spawn_success")]:
        result = subprocess.run(
            [sys.executable, str(script), str(blocked), str(safe), mode],
            env=env,
            capture_output=True,
            text=True,
            timeout=12,
            check=True,
        )
        if mode == "safe":
            assert result.stdout.strip() == expected
        else:
            assert result.stdout.startswith(expected + ":")
            assert "PermissionError" in result.stderr + result.stdout
