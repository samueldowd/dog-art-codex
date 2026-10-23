"""Actual save-boundary crash recovery never issues another paid submission."""

import base64
import io
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from dog_art.clock import FrozenClock
from dog_art.contracts import DogDescription
from dog_art.portraits import PortraitError, PortraitService
from dog_art.safety import sha256
from dog_art.settings import Settings
from dog_art.storage import Store


class ProcessDeath(BaseException):
    """Bypass ordinary exception handlers, as a process crash would."""


def png(color=(170, 105, 35, 255)):
    image = Image.new("RGBA", (512, 512))
    ImageDraw.Draw(image).ellipse((60, 50, 450, 460), fill=color)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class PaidAPI:
    def __init__(self):
        self.calls = 0
        self.bytes = png()

    def edit(self, **kwargs):
        self.calls += 1
        if self.calls > 1:
            pytest.fail("recovery must never submit a second paid request")
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(self.bytes).decode())],
            usage=None,
            _request_id="saved-response-id",
        )


def setup(tmp_path):
    root = tmp_path.resolve() / "state"
    store = Store(root / "catalog.sqlite")
    store.db.execute("INSERT INTO dogs VALUES('dog1',0,'accepted',NULL)")
    settings = Settings(
        {
            "APP_DATA_ROOT": str(root),
            "MIN_FREE_DISK_MB": 0,
            "OPENAI_IMAGE_MODEL": "synthetic-image-model",
            "OPENAI_IMAGE_SIZE": "1024x1024",
            "OPENAI_IMAGE_QUALITY": "medium",
            "OPENAI_REFERENCE_MODE": "artwork_only",
            "ALLOW_CAMERA_CROP_UPLOAD": False,
            "OPENAI_GENERATION_ENABLED": True,
            "OPENAI_DAILY_BUDGET_USD": 2,
            "OPENAI_MAX_CALLS_PER_DAY": 2,
            "WORKER_CONCURRENCY": 1,
        },
        {"OPENAI_API_KEY": "offline-sentinel"},
    )
    paid = PaidAPI()
    service = PortraitService(
        store,
        settings,
        FrozenClock(datetime(2026, 10, 22, 16, tzinfo=UTC)),
        client=SimpleNamespace(images=paid),
    )
    return service, store, paid


def generate(service):
    return service.generate("dog1", DogDescription(coat_colors=("brown",)), reserve_usd=1)


def restart(service, store):
    path = store.path
    store.close()
    reopened = Store(path)
    recovered = PortraitService(reopened, service.settings, service.clock, client=service.client)
    recovered.ledger.recover()
    return recovered, reopened


def expected_path(service, store):
    row = store.db.execute("SELECT * FROM portraits").fetchone()
    recipe = json.loads(row["recipe"])
    return (
        Path(service.settings["APP_DATA_ROOT"])
        / "portraits"
        / "dog1"
        / (recipe["recipe_hash"] + ".png")
    )


@pytest.mark.parametrize(
    "boundary", ["partial_fsync", "replace", "path_update", "review_transition"]
)
def test_actual_generation_crash_boundaries_recover_without_paid_call(
    tmp_path, monkeypatch, boundary
):
    service, store, paid = setup(tmp_path)
    with monkeypatch.context() as patch:
        if boundary == "partial_fsync":
            real = os.fsync

            def crash(fd):
                real(fd)
                raise ProcessDeath("after complete partial write")

            patch.setattr(os, "fsync", crash)
        elif boundary == "replace":
            real = Path.replace

            def crash(path, destination):
                real(path, destination)
                raise ProcessDeath("after replace before path update")

            patch.setattr(Path, "replace", crash)
        else:
            real = service.ledger.transition

            def crash(request_id, expected, state, **kwargs):
                if expected == "succeeded" and state == "needs_review":
                    if boundary == "review_transition":
                        real(request_id, expected, state, **kwargs)
                    raise ProcessDeath("after path update")
                return real(request_id, expected, state, **kwargs)

            patch.setattr(service.ledger, "transition", crash)
        with pytest.raises(ProcessDeath):
            generate(service)
    output = expected_path(service, store)
    staging = output.with_suffix(".partial")
    assert output.exists() or staging.exists()
    original = (output if output.exists() else staging).read_bytes()
    service, store = restart(service, store)
    results = service.recover_saved()
    assert results[0]["recovered"] is True
    assert results[0]["state"] == "needs_review" and results[0]["error_code"] is None
    assert results[0]["qa"]["visual_review"].startswith("required")
    assert output.read_bytes() == original
    assert output.stat().st_mode & 0o777 == 0o600
    row = store.db.execute("SELECT * FROM portraits").fetchone()
    assert row["path"] == str(output) and row["sha256"] == sha256(output)
    assert row["request_id"] == results[0]["request_id"]
    assert row["state"] == "needs_review"
    assert store.db.execute("SELECT state FROM requests").fetchone()[0] == "needs_review"
    assert paid.calls == 1 and store.db.execute("SELECT count(*) FROM requests").fetchone()[0] == 1
    assert service.recover_saved()[0]["recovered"] is False
    assert (
        store.db.execute(
            "SELECT count(*) FROM audit WHERE code='portrait_saved_recovered'"
        ).fetchone()[0]
        == 1
    )
    with pytest.raises(PortraitError, match="no automatic resubmission"):
        generate(service)
    assert paid.calls == 1
    store.close()


@pytest.mark.parametrize(
    "problem",
    [
        "missing",
        "corrupt_png",
        "incomplete_partial",
        "wrong_hash",
        "conflicting_partial",
        "wrong_path",
        "symlink_png",
        "symlink_partial",
    ],
)
def test_bad_or_missing_output_is_persistent_manual_hold_and_never_resubmits(tmp_path, problem):
    service, store, paid = setup(tmp_path)
    generate(service)
    output = expected_path(service, store)
    partial = output.with_suffix(".partial")
    original = output.read_bytes()
    if problem == "missing":
        output.unlink()
    elif problem == "corrupt_png":
        output.write_bytes(b"incomplete PNG")
    elif problem == "incomplete_partial":
        output.unlink()
        partial.write_bytes(original[:100])
    elif problem == "wrong_hash":
        store.db.execute("UPDATE portraits SET sha256=?", ("0" * 64,))
    elif problem == "conflicting_partial":
        partial.write_bytes(png((20, 30, 40, 255)))
    elif problem == "wrong_path":
        store.db.execute("UPDATE portraits SET path=?", (str(output.parent / "other.png"),))
    elif problem == "symlink_png":
        actual = output.parent / "unbound.png"
        output.rename(actual)
        output.symlink_to(actual)
    elif problem == "symlink_partial":
        partial.symlink_to(output)
    before = {p.name: p.read_bytes() for p in output.parent.iterdir() if p.is_file()}
    result = service.recover_saved()[0]
    assert not result["recovered"] and result["error_code"].startswith("saved_portrait_")
    assert result["state"] == "needs_review"
    assert (
        store.db.execute("SELECT error_code FROM portraits").fetchone()[0] == result["error_code"]
    )
    assert before == {p.name: p.read_bytes() for p in output.parent.iterdir() if p.is_file()}
    with pytest.raises(PortraitError, match="no automatic resubmission"):
        generate(service)
    assert paid.calls == 1
    assert service.recover_saved()[0]["error_code"] == result["error_code"]
    assert (
        store.db.execute(
            "SELECT count(*) FROM audit WHERE code='portrait_saved_recovery_hold'"
        ).fetchone()[0]
        == 1
    )
    store.close()


def test_unbound_files_and_indeterminate_request_are_never_adopted(tmp_path):
    service, store, paid = setup(tmp_path)
    loose = Path(service.settings["APP_DATA_ROOT"]) / "portraits" / "dog1" / ("a" * 64 + ".png")
    loose.parent.mkdir(parents=True)
    loose.write_bytes(png())
    assert service.recover_saved() == []
    assert store.db.execute("SELECT count(*) FROM portraits").fetchone()[0] == 0
    generate(service)
    row = store.db.execute("SELECT recipe_key FROM portraits").fetchone()
    store.db.execute("UPDATE requests SET state='indeterminate'")
    store.db.execute("UPDATE portraits SET state='indeterminate',path=NULL,sha256=NULL")
    assert service.recover_saved() == []
    assert (
        store.db.execute("SELECT path FROM portraits WHERE recipe_key=?", row).fetchone()[0] is None
    )
    assert paid.calls == 1 and loose.exists()
    store.close()


@pytest.mark.parametrize("change", ["dog", "hash", "style", "request_id"])
def test_persisted_recipe_request_binding_mismatch_is_not_adopted(tmp_path, change):
    service, store, paid = setup(tmp_path)
    generate(service)
    row = store.db.execute("SELECT * FROM portraits").fetchone()
    recipe = json.loads(row["recipe"])
    if change == "dog":
        recipe["dog_id"] = "other"
    elif change == "hash":
        recipe["recipe_hash"] = "../../private"
    elif change == "style":
        recipe["style_version"] = "other"
    else:
        store.db.execute("UPDATE portraits SET request_id='unbound-request'")
    store.db.execute("UPDATE portraits SET recipe=?,path=NULL,sha256=NULL", (json.dumps(recipe),))
    result = service.recover_saved()[0]
    assert result["error_code"] == "saved_portrait_binding_invalid"
    assert store.db.execute("SELECT path FROM portraits").fetchone()[0] is None
    assert paid.calls == 1
    store.close()


def test_recovery_db_crash_rolls_back_metadata_and_can_resume_linked_partial(tmp_path, monkeypatch):
    service, store, paid = setup(tmp_path)

    def crash_after_partial(path, destination):
        raise ProcessDeath("before replace")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", crash_after_partial)
        with pytest.raises(ProcessDeath):
            generate(service)
    output = expected_path(service, store)
    assert output.with_suffix(".partial").exists() and not output.exists()

    def crash_audit(*args, **kwargs):
        raise ProcessDeath("during atomic metadata update")

    with monkeypatch.context() as patch:
        patch.setattr(store, "audit", crash_audit)
        with pytest.raises(ProcessDeath):
            service.recover_saved()
    assert output.exists()
    assert store.db.execute("SELECT path FROM portraits").fetchone()[0] is None
    assert store.db.execute("SELECT state FROM requests").fetchone()[0] == "succeeded"
    service, store = restart(service, store)
    assert service.recover_saved()[0]["recovered"] is True
    assert paid.calls == 1 and output.read_bytes() == paid.bytes
    store.close()


def test_recovery_never_overwrites_a_final_file_created_during_partial_install(
    tmp_path, monkeypatch
):
    service, store, paid = setup(tmp_path)

    def crash(path, destination):
        raise ProcessDeath("before replace")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", crash)
        with pytest.raises(ProcessDeath):
            generate(service)
    output = expected_path(service, store)
    other = png((1, 2, 3, 255))
    real_link = os.link

    def race(source, destination, **kwargs):
        Path(destination).write_bytes(other)
        return real_link(source, destination, **kwargs)

    monkeypatch.setattr(os, "link", race)
    result = service.recover_saved()[0]
    assert result["error_code"] == "saved_portrait_conflict"
    assert output.read_bytes() == other
    assert output.with_suffix(".partial").read_bytes() == paid.bytes
    assert paid.calls == 1
    store.close()


def test_recovery_uses_same_paid_barrier_as_generator(tmp_path):
    import threading

    from dog_art.daily import application_lock

    service, store, paid = setup(tmp_path)
    generate(service)
    started, finished = threading.Event(), threading.Event()
    results, errors = [], []

    def recover_in_thread():
        local = Store(store.path)
        try:
            other = PortraitService(local, service.settings, service.clock)
            started.set()
            results.extend(other.recover_saved())
        except BaseException as error:
            errors.append(error)
        finally:
            local.close()
            finished.set()

    lock = Path(service.settings["APP_DATA_ROOT"]) / "locks/paid.lock"
    with application_lock(lock):
        thread = threading.Thread(target=recover_in_thread)
        thread.start()
        assert started.wait(2)
        assert not finished.wait(0.05)
    assert finished.wait(2)
    thread.join()
    assert not errors and results[0]["state"] == "needs_review"
    assert paid.calls == 1
    store.close()
