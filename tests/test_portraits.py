import base64
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from dog_art.clock import FrozenClock
from dog_art.contracts import DogDescription
from dog_art.portraits import PortraitError, PortraitService, validate_png
from dog_art.settings import Settings, load_settings
from dog_art.storage import Store

ROOT = Path(__file__).resolve().parents[1]


class FakeImages:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def edit(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise TimeoutError("private sensitive message")
        data = (ROOT / "assets/style/dog-watercolor-transparent.png").read_bytes()
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(data).decode())],
            usage=None,
            _request_id="request",
        )


def setup(tmp_path, fail=False):
    cfg = load_settings(ROOT / "config/app.toml", tmp_path / ".env", environ={})
    values = {
        **cfg.values,
        "APP_DATA_ROOT": str(tmp_path / "state"),
        "OPENAI_GENERATION_ENABLED": True,
        "MIN_FREE_DISK_MB": 0,
    }
    settings = Settings(values, {"OPENAI_API_KEY": "test-sentinel"})
    store = Store(tmp_path / "state/catalog.sqlite")
    store.db.execute("INSERT INTO dogs VALUES('dog1',0,'accepted',NULL)")
    fake = FakeImages(fail)
    service = PortraitService(
        store,
        settings,
        FrozenClock(datetime(2026, 10, 22, 12, tzinfo=UTC)),
        client=SimpleNamespace(images=fake),
    )
    service.ledger.set_build_scope("test-build", 2)
    return service, store, fake


def test_generation_review_reuse_privacy(tmp_path):
    service, store, fake = setup(tmp_path)
    description = DogDescription(coat_colors=("black",), uncertainty=("tail not visible",))
    result = service.generate("dog1", description, reserve_usd=1, build_scope="test-build")
    assert result["state"] == "needs_review" and len(fake.calls) == 1
    call = fake.calls[0]
    assert call["image"][0] == "generated-style.png" and call["n"] == 1
    assert call["background"] == "transparent" and "tail not visible" in call["prompt"]
    key = store.db.execute("SELECT recipe_key FROM portraits").fetchone()[0]
    service.accept(key, reviewer="test-reviewer", evidence="synthetic test approved style fixture")
    again = service.generate(
        "dog1",
        DogDescription(coat_colors=("black",), pose="walking"),
        reserve_usd=1,
        build_scope="test-build",
    )
    assert again["new_request"] is False and len(fake.calls) == 1
    store.close()


def test_indeterminate_no_retry(tmp_path):
    service, store, fake = setup(tmp_path, True)
    for _ in range(2):
        with pytest.raises(PortraitError):
            service.generate(
                "dog1",
                DogDescription(coat_colors=("black",)),
                reserve_usd=1,
                build_scope="test-build",
            )
    assert len(fake.calls) == 1 and store.status()["requests"] == {"indeterminate": 1}
    store.close()


def test_matte_and_corrupt_rejected():
    import io

    from PIL import Image

    b = io.BytesIO()
    Image.new("RGBA", (512, 512), "white").save(b, format="PNG")
    with pytest.raises(PortraitError, match="exterior"):
        validate_png(b.getvalue())
    with pytest.raises(PortraitError, match="decode"):
        validate_png(b"not an image")


def test_acceptance_and_dependency_wake_are_atomic_and_recoverable(tmp_path, monkeypatch):
    import json

    service, store, fake = setup(tmp_path)
    service.generate(
        "dog1", DogDescription(coat_colors=("black",)), reserve_usd=1, build_scope="test-build"
    )
    key = store.db.execute("SELECT recipe_key FROM portraits").fetchone()[0]
    store.db.execute("INSERT INTO days VALUES('2026-10-20','old',1,0)")
    store.db.execute("INSERT INTO membership VALUES('2026-10-20','dog1',0,1)")
    original = store.enqueue

    def crash(*args, **kwargs):
        raise RuntimeError("crash during dependency wake")

    monkeypatch.setattr(store, "enqueue", crash)
    with pytest.raises(RuntimeError):
        service.accept(key, reviewer="test", evidence="test fixture")
    assert store.db.execute("SELECT state FROM portraits").fetchone()[0] == "needs_review"
    assert (
        store.db.execute("SELECT count(*) FROM audit WHERE code='portrait_validated'").fetchone()[0]
        == 0
    )
    monkeypatch.setattr(store, "enqueue", original)
    service.accept(key, reviewer="test", evidence="test fixture")
    job = store.db.execute("SELECT job_id,payload FROM jobs WHERE kind='collage'").fetchone()
    assert json.loads(job["payload"])["day"] == "2026-10-20"
    # Reconcile an older catalog that committed validation before the wake.
    store.db.execute("DELETE FROM jobs WHERE job_id=?", (job["job_id"],))
    service.accept(key, reviewer="test", evidence="recover previous acceptance")
    assert store.db.execute("SELECT count(*) FROM jobs WHERE kind='collage'").fetchone()[0] == 1
    assert len(fake.calls) == 1
    store.close()


@pytest.mark.parametrize("coat_colors", [(), ("unknown",)])
def test_wholly_unknown_appearance_never_reserves_or_calls_api(tmp_path, coat_colors):
    service, store, fake = setup(tmp_path)
    with pytest.raises(PortraitError, match="no observed appearance facts"):
        service.generate(
            "dog1",
            DogDescription(
                coat_colors=coat_colors,
                visible_areas=("blurred body",),
                uncertainty=("image blurred",),
            ),
            reserve_usd=1,
            build_scope="test-build",
        )
    assert fake.calls == [] and store.db.execute("SELECT count(*) FROM requests").fetchone()[0] == 0
    store.close()


@pytest.mark.parametrize(
    "phrase", ["not clearly visible", "cannot be determined from this image", "unknown due to blur"]
)
def test_unknown_explanations_never_justify_paid_art(tmp_path, phrase):
    service, store, fake = setup(tmp_path)
    with pytest.raises(PortraitError, match="no observed appearance facts"):
        service.generate(
            "dog1", DogDescription(markings=phrase), reserve_usd=1, build_scope="test-build"
        )
    assert fake.calls == [] and store.db.execute("SELECT count(*) FROM requests").fetchone()[0] == 0
    store.close()


def test_observed_negative_marking_is_a_fact():
    from dog_art.description import has_observed_appearance

    assert has_observed_appearance(DogDescription(markings="no white patches"))


def test_saved_portrait_replay_needs_no_new_facts_key_or_generation_permission(tmp_path):
    from dataclasses import replace

    service, store, fake = setup(tmp_path)
    service.generate(
        "dog1", DogDescription(coat_colors=("black",)), reserve_usd=1, build_scope="test-build"
    )
    key = store.db.execute("SELECT recipe_key FROM portraits").fetchone()[0]
    service.accept(key, reviewer="test", evidence="fixture alpha/visual review")
    service.settings = replace(
        service.settings,
        values={**service.settings.values, "OPENAI_GENERATION_ENABLED": False},
        secrets={},
    )
    result = service.generate("dog1", DogDescription(), reserve_usd=1, build_scope="test-build")
    assert (
        result["new_request"] is False and result["state"] == "validated" and len(fake.calls) == 1
    )
    assert store.db.execute("SELECT count(*) FROM requests").fetchone()[0] == 1
    store.close()
