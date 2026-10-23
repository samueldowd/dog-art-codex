"""Privileged launchers exclude app-writable import paths without broadening access."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    "install-release.sh",
    "activate-live.template.sh",
    "upgrade-ready.template.sh",
    "resume-live-34ac27e.sh",
)


def test_isolated_interpreter_ignores_harmless_app_writable_json_module(tmp_path):
    (tmp_path / "json.py").write_text("APP_WRITABLE_IMPORT_SENTINEL = True\n")
    program = "import json; print(getattr(json, 'APP_WRITABLE_IMPORT_SENTINEL', False))"
    ordinary = subprocess.run(
        [sys.executable, "-c", program],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    isolated = subprocess.run(
        [sys.executable, "-I", "-c", program],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert ordinary.stdout.strip() == "True"
    assert isolated.stdout.strip() == "False"


@pytest.mark.parametrize("name", SCRIPTS)
def test_privileged_script_python_commands_are_isolated_and_cwd_is_accessible(name):
    text = (ROOT / "scripts" / name).read_text()
    commands = []
    for number, line in enumerate(text.splitlines(), 1):
        match = re.search(r'(?:python3|"\$(?:release|prior)/venv/bin/python")\s+(.+)', line)
        if match:
            commands.append(number)
            assert match[1].startswith("-I "), f"{name}:{number}: Python must use -I"
    assert commands, f"{name}: expected explicit isolated Python commands"
    # Root and dedicated-user children share a traversable, non-app-writable cwd.
    assert "\ncd /\n" in text
    assert text.index("\ncd /\n") < text.index("runuser -u dog-art")
