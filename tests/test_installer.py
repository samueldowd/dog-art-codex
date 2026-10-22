"""Exercise the real installer shell with isolated paths and fake host boundaries."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def harness(tmp_path, *, upgrade=False, fail_verify=False, fail_restart=False):
    virtual = tmp_path / "host"
    app = virtual / "opt/dog-art"
    etc = virtual / "etc/dog-art"
    units = virtual / "etc/systemd/system"
    state = virtual / "var/lib/dog-art"
    delivery = tmp_path / "delivery"
    tools = tmp_path / "bin"
    for d in (
        app / "releases",
        etc,
        units,
        state,
        delivery / "wheel",
        delivery / "config",
        delivery / "deploy/systemd",
        tools,
    ):
        d.mkdir(parents=True, exist_ok=True)
    (etc / ".env").write_text("")
    (delivery / "SHA256SUMS").write_text("test harness boundary")
    (delivery / "SOURCE_REVISION").write_text("a" * 40 + "\n")
    (delivery / "requirements.lock").write_text("")
    (delivery / "wheel/runtime.whl").write_text("")
    (delivery / "config/app.toml.example").write_text("test app")
    for name in ("dog-art.service", "dog-art-reset.service", "dog-art-reset.timer"):
        (delivery / "deploy/systemd" / name).write_text(
            (ROOT / "deploy/systemd" / name).read_text().replace("/opt/dog-art", str(app))
        )
    if upgrade:
        prior = app / "releases/previous"
        prior.mkdir()
        (app / "current").symlink_to(prior)
        for name in ("dog-art.service", "dog-art-reset.service", "dog-art-reset.timer"):
            (units / name).write_text("previous " + name)
    script = (ROOT / "scripts/install-release.sh").read_text()
    for base in (
        "/opt/dog-art",
        "/etc/dog-art",
        "/etc/systemd/system",
        "/var/lib/dog-art",
        "/proc",
    ):
        script = script.replace(base, str(virtual / base.lstrip("/")))
    installer = tmp_path / "install.sh"
    installer.write_text(script)
    log = tmp_path / "calls"
    mock = tools / "boundary"
    mock.write_text(
        "#!"
        + sys.executable
        + "\n"
        + """
import os,sys,pathlib,subprocess
name=pathlib.Path(sys.argv[0]).name;a=sys.argv[1:];v=pathlib.Path(os.environ['VIRTUAL']); log=pathlib.Path(os.environ['CALL_LOG'])
with log.open('a') as f:f.write(name+' '+' '.join(a)+'\\n')
if name=='id':print('0')
elif name=='hostname':print('CT112')
elif name=='df':print('Filesystem M Used Available Capacity Mount\\nfake 40000 4000 36000 10% /')
elif name in ('getent','sha256sum','chown','chmod'):pass
elif name=='install':
 args=[];i=0
 while i<len(a):
  if a[i] in ('-o','-g','-m'):i+=2
  elif a[i]=='-d':i+=1
  else:args.append(a[i]);i+=1
 if '-d' in a:
  for p in args:pathlib.Path(p).mkdir(parents=True,exist_ok=True)
 else:
  import shutil
  for p in args[:-1]:shutil.copyfile(p,args[-1])
elif name=='mv':os.replace(a[-2],a[-1])
elif name=='python3':
 dest=pathlib.Path(a[-1]);(dest/'bin').mkdir(parents=True)
 for exe in ('python','dog-art'):
  p=dest/'bin'/exe;p.write_text('#!/bin/sh\\nexit 0\\n');p.chmod(0o755)
elif name=='runuser':sys.exit(subprocess.call(a[a.index('--')+1:]))
elif name=='systemd-analyze':
 if os.environ.get('FAIL_VERIFY')=='1':sys.exit(1)
 for p in a[1:]:
  text=pathlib.Path(p).read_text()
  if 'ExecStart=' in text:
   executable=text.split('ExecStart=')[1].split()[0]
   assert pathlib.Path(executable).is_file(),executable
elif name=='systemctl':
 if a[0]=='is-enabled':print('enabled' if os.environ['UPGRADE']=='1' else 'disabled');sys.exit(0 if os.environ['UPGRADE']=='1' else 1)
 if a[0]=='is-active':
  if '--quiet' not in a:print('active' if os.environ['UPGRADE']=='1' else 'inactive')
  sys.exit(0 if '--quiet' in a or os.environ['UPGRADE']=='1' else 3)
 if a[0]=='restart':
  if os.environ.get('FAIL_RESTART')=='1':sys.exit(1)
  release=(v/'opt/dog-art/current').resolve();p=v/'proc/123';p.mkdir(parents=True,exist_ok=True)
  (p/'cmdline').write_bytes(b'python\\0'+str(release/'venv/bin/dog-art').encode()+b'\\0')
 if a[0]=='show':print('123')
else:raise AssertionError(name)
"""
    )
    mock.chmod(0o755)
    for name in (
        "mv",
        "id",
        "hostname",
        "df",
        "getent",
        "sha256sum",
        "chown",
        "chmod",
        "install",
        "python3",
        "runuser",
        "systemd-analyze",
        "systemctl",
    ):
        (tools / name).symlink_to(mock)
    env = {
        **os.environ,
        "PATH": str(tools) + ":" + os.environ["PATH"],
        "VIRTUAL": str(virtual),
        "CALL_LOG": str(log),
        "UPGRADE": str(int(upgrade)),
        "FAIL_VERIFY": str(int(fail_verify)),
        "FAIL_RESTART": str(int(fail_restart)),
    }
    result = subprocess.run(
        ["/bin/sh", str(installer), str(delivery), "a" * 40],
        env=env,
        capture_output=True,
        text=True,
    )
    return result, app, units, log.read_text()


@pytest.mark.parametrize("upgrade", [False, True])
def test_first_install_and_upgrade_restart_and_verify_running_revision(tmp_path, upgrade):
    r, app, units, log = harness(tmp_path, upgrade=upgrade)
    assert r.returncode == 0, r.stderr + r.stdout
    assert (app / "current").resolve().name == "0.1.0-" + "a" * 40
    assert "systemctl restart dog-art.service dog-art-reset.timer" in log
    assert (
        str((app / "current").resolve() / "venv/bin/dog-art")
        in (units / "dog-art.service").read_text()
    )
    if upgrade:
        assert log.index("systemd-analyze verify") < log.index("systemctl stop")


def test_failed_staged_verification_does_not_modify_live_units_or_pointer(tmp_path):
    r, app, units, log = harness(tmp_path, upgrade=True, fail_verify=True)
    assert r.returncode != 0
    assert (app / "current").resolve().name == "previous"
    assert (units / "dog-art.service").read_text() == "previous dog-art.service"
    assert "systemctl stop" not in log


def test_failed_upgrade_restores_previous_pointer_units_and_services(tmp_path):
    r, app, units, log = harness(tmp_path, upgrade=True, fail_restart=True)
    assert r.returncode != 0
    assert (app / "current").resolve().name == "previous"
    assert (units / "dog-art.service").read_text() == "previous dog-art.service"
    assert "systemctl start dog-art.service" in log
