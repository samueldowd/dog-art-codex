"""Acceptance failures must restore the verified image or expose durable repair evidence."""

import importlib.util
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from dog_art.clock import FrozenClock
from dog_art.settings import Settings

spec = importlib.util.spec_from_file_location(
    "installed_acceptance", Path(__file__).parents[1] / "scripts/verify-installed.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def png(color):
    out = io.BytesIO()
    Image.new("RGB", (1920, 1080), color).save(out, format="PNG")
    return out.getvalue()


class Transport:
    def __init__(self):
        self.files = {"kitchen-tv/dog-art/dog-collage.png": png("black")}
        self.fail = False

    def read(self, path):
        return self.files[path]

    def write_new(self, path, data):
        assert path not in self.files
        self.files[path] = data

    def replace(self, source, target):
        if self.fail:
            raise OSError("refused")
        self.files[target] = self.files.pop(source)

    def remove_owned_temp(self, path):
        if path not in self.files:
            raise FileNotFoundError()
        del self.files[path]

    def close(self):
        pass


def setup(tmp_path):
    settings = Settings(
        {
            "APP_DATA_ROOT": str(tmp_path),
            "SMB_HOST": "ha.test",
            "SMB_SHARE": "media",
            "SMB_SUBDIRECTORY": "kitchen-tv/dog-art",
            "PUBLISH_FILENAME": "dog-collage.png",
            "COLLAGE_BACKGROUND": "#F3EBDD",
        },
        {},
    )
    clock = FrozenClock(datetime(2026, 10, 22, 16, tzinfo=UTC))
    transport = Transport()
    return settings, clock, transport


def test_failure_immediately_after_blank_restores_original_bytes(tmp_path):
    settings, clock, transport = setup(tmp_path)
    target = "kitchen-tv/dog-art/dog-collage.png"
    original = transport.files[target]
    with pytest.raises(ValueError, match="injected"):
        with module.owned_image_checkpoint(settings, tmp_path, clock, factory=lambda s: transport):
            transport.files[target] = png("#F3EBDD")
            raise ValueError("injected after blank")
    assert transport.files[target] == original
    assert json.loads((tmp_path / "display-checkpoint.json").read_text())["state"] == "restored"


def test_restore_outage_is_durable_and_recovers_without_paid_or_unrelated_writes(tmp_path):
    settings, clock, transport = setup(tmp_path)
    target = "kitchen-tv/dog-art/dog-collage.png"
    original = transport.files[target]
    transport.files["unrelated.png"] = b"unrelated"
    with pytest.raises(RuntimeError, match="restoration blocked"):
        with module.owned_image_checkpoint(settings, tmp_path, clock, factory=lambda s: transport):
            transport.files[target] = png("#F3EBDD")
            transport.fail = True
            raise ValueError("failure during restore")
    pending = json.loads((tmp_path / "display-checkpoint.json").read_text())
    assert pending["state"] == "restoration_blocked"
    assert pending["error_code"] == "owned_image_restore_failed"
    transport.fail = False
    module.restore_checkpoint(settings, tmp_path, clock, factory=lambda s: transport)
    assert transport.files == {target: original, "unrelated.png": b"unrelated"}


def test_crossing_midnight_never_restores_prior_day_dog_snapshot(tmp_path):
    settings, clock, transport = setup(tmp_path)
    with module.owned_image_checkpoint(settings, tmp_path, clock, factory=lambda s: transport):
        clock.value += timedelta(days=1)
    with Image.open(io.BytesIO(transport.files["kitchen-tv/dog-art/dog-collage.png"])) as image:
        assert image.getextrema() == ((243, 243), (235, 235), (221, 221))


@pytest.mark.parametrize("boundary", ["replace", "readback"])
def test_midnight_during_final_network_restore_corrects_old_dog_before_success(tmp_path, boundary):
    settings, clock, transport = setup(tmp_path)
    clock.value = datetime(2026, 10, 23, 3, 59, 59, tzinfo=UTC)
    replaced = False
    crossed = False
    real_replace, real_read = transport.replace, transport.read

    def crossing_replace(source, target):
        nonlocal replaced, crossed
        real_replace(source, target)
        replaced = True
        if boundary == "replace" and not crossed:
            clock.value += timedelta(seconds=2)
            crossed = True

    def crossing_read(path):
        nonlocal crossed
        data = real_read(path)
        if boundary == "readback" and replaced and path.endswith("dog-collage.png") and not crossed:
            clock.value += timedelta(seconds=2)
            crossed = True
        return data

    transport.replace = crossing_replace
    transport.read = crossing_read
    with module.owned_image_checkpoint(settings, tmp_path, clock, factory=lambda s: transport):
        transport.files["kitchen-tv/dog-art/dog-collage.png"] = png("white")
    assert crossed
    with Image.open(io.BytesIO(transport.files["kitchen-tv/dog-art/dog-collage.png"])) as image:
        assert image.getextrema() == ((243, 243), (235, 235), (221, 221))
    receipt = json.loads((tmp_path / "display-checkpoint.json").read_text())
    assert receipt["state"] == "restored" and receipt["restored_day"] == "2026-10-23"


@pytest.mark.parametrize("boundary", ["replace", "directory_fsync"])
def test_interrupted_checkpoint_update_preserves_complete_recovery_ledger(
    tmp_path, monkeypatch, boundary
):
    path = tmp_path / "display-checkpoint.json"
    before = {"state": "captured", "sha256": "a" * 64}
    after = {"state": "restoration_pending", "sha256": "a" * 64}
    module.write_checkpoint(path, before)
    real_replace, real_fsync = module.os.replace, module.os.fsync
    calls = 0

    def interrupted_replace(*args, **kwargs):
        raise KeyboardInterrupt("kill at replace boundary")

    def interrupted_fsync(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt("kill at directory fsync")
        return real_fsync(fd)

    monkeypatch.setattr(
        module.os, "replace", interrupted_replace if boundary == "replace" else real_replace
    )
    monkeypatch.setattr(
        module.os, "fsync", interrupted_fsync if boundary == "directory_fsync" else real_fsync
    )
    with pytest.raises(KeyboardInterrupt):
        module.write_checkpoint(path, after)
    assert json.loads(path.read_text()) == (before if boundary == "replace" else after)


def test_snapshot_read_crossing_midnight_is_never_mislabeled_new_day(tmp_path):
    settings, clock, transport = setup(tmp_path)
    clock.value = datetime(2026, 10, 23, 3, 59, 59, tzinfo=UTC)
    real_read = transport.read
    crossed = False

    def crossing_read(path):
        nonlocal crossed
        result = real_read(path)
        if not crossed:
            clock.value += timedelta(seconds=2)
            crossed = True
        return result

    transport.read = crossing_read
    with module.owned_image_checkpoint(settings, tmp_path, clock, factory=lambda s: transport):
        pass
    receipt = json.loads((tmp_path / "display-checkpoint.json").read_text())
    assert receipt["day"] == "2026-10-22" and receipt["restored_day"] == "2026-10-23"
    with Image.open(io.BytesIO(transport.files["kitchen-tv/dog-art/dog-collage.png"])) as image:
        assert image.getextrema() == ((243, 243), (235, 235), (221, 221))


def test_delayed_operator_run_uses_dated_baseline_instead_of_capture_day(tmp_path):
    settings, clock, transport = setup(tmp_path)
    clock.value += timedelta(days=1)
    original = transport.files["kitchen-tv/dog-art/dog-collage.png"]
    import hashlib

    with module.owned_image_checkpoint(
        settings,
        tmp_path,
        clock,
        factory=lambda s: transport,
        baseline_day="2026-10-22",
        baseline_sha256=hashlib.sha256(original).hexdigest(),
    ):
        pass
    with Image.open(io.BytesIO(transport.files["kitchen-tv/dog-art/dog-collage.png"])) as image:
        assert image.getextrema() == ((243, 243), (235, 235), (221, 221))


def test_mismatched_dated_baseline_stops_before_display_mutation(tmp_path):
    settings, clock, transport = setup(tmp_path)
    original = dict(transport.files)
    with pytest.raises(ValueError, match="dated reviewed baseline"):
        with module.owned_image_checkpoint(
            settings,
            tmp_path,
            clock,
            factory=lambda s: transport,
            baseline_day="2026-10-22",
            baseline_sha256="b" * 64,
        ):
            raise AssertionError("must not enter exercise")
    assert transport.files == original and not (tmp_path / "display-checkpoint.json").exists()
