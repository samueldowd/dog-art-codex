"""Reset must publish before incomplete/current-day composition, without data loss."""

import io
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from PIL import Image, ImageDraw

from dog_art.clock import FrozenClock
from dog_art.daily import DailyManager, PortraitPendingError, StalePublication
from dog_art.publishing import Publisher, PublishError
from dog_art.safety import sha256
from dog_art.settings import Settings
from dog_art.storage import Store

TARGET = "kitchen-tv/dog-art/dog-collage.png"


class MemorySMB:
    def __init__(self):
        old = io.BytesIO()
        Image.new("RGB", (1920, 1080), "blue").save(old, format="PNG")
        self.files = {TARGET: old.getvalue(), "kitchen-tv/unrelated.png": b"unchanged"}
        self.fail = False

    def read(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def write_new(self, path, data):
        assert path not in self.files
        self.files[path] = data

    def replace(self, source, target):
        if self.fail:
            raise OSError("controlled outage")
        self.files[target] = self.files.pop(source)

    def remove_owned_temp(self, path):
        self.files.pop(path, None)


def setup(tmp_path):
    root = tmp_path.resolve() / "state"
    settings = Settings(
        {
            "APP_DATA_ROOT": str(root),
            "MIN_FREE_DISK_MB": 0,
            "COLLAGE_WIDTH": 1920,
            "COLLAGE_HEIGHT": 1080,
            "DAY_TIMEZONE": "America/New_York",
            "PUBLISH_ENABLED": True,
            "SMB_HOST": "ha.example",
            "SMB_SHARE": "media",
            "SMB_SUBDIRECTORY": "kitchen-tv/dog-art",
            "PUBLISH_FILENAME": "dog-collage.png",
        },
        {"SMB_USERNAME": "offline", "SMB_PASSWORD": "offline"},
    )
    store = Store(root / "catalog.sqlite")
    clock = FrozenClock(datetime(2026, 10, 22, 16, tzinfo=UTC))
    daily = DailyManager(store, settings, clock)
    transport = MemorySMB()
    return store, settings, clock, daily, transport


def dog(store, settings, name="dog-a", ready=False):
    store.db.execute("INSERT INTO dogs VALUES(?,0,'accepted',NULL)", (name,))
    if ready:
        from pathlib import Path

        path = Path(settings["APP_DATA_ROOT"]) / "portraits" / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGBA", (512, 512))
        ImageDraw.Draw(image).ellipse((50, 50, 460, 460), fill=(100, 50, 25, 255))
        image.save(path)
        store.db.execute(
            "INSERT INTO portraits(recipe_key,dog_id,recipe,state,path,sha256) VALUES(?,?,'{}','validated',?,?)",
            ("recipe-" + name, name, str(path), sha256(path)),
        )


def publish(store, settings, clock, daily, transport, revision=None):
    return Publisher(store, settings, clock, daily, transport=transport).publish(
        revision or daily.latest()
    )


def assert_blank(data):
    with Image.open(io.BytesIO(data)) as image:
        assert image.mode == "RGB" and image.size == (1920, 1080)
        assert image.getextrema() == ((243, 243), (235, 235), (221, 221))


def test_new_day_sighting_before_timer_preserves_priority_blank_and_all_members(tmp_path):
    store, settings, clock, daily, transport = setup(tmp_path)
    daily.reconcile()
    publish(store, settings, clock, daily, transport)
    dog(store, settings)
    daily.record_sighting("dog-a", clock.now())
    clock.value = datetime(2026, 10, 23, 4, tzinfo=UTC)
    daily.record_sighting("dog-a", clock.now())
    state = daily.reconcile()
    assert state.day == "2026-10-23" and state.dog_ids == ("dog-a",) and state.revision == 1
    reset = daily.latest()
    assert reset.day == state.day and reset.revision == 0 and reset.dog_ids == ()
    assert (
        store.db.execute(
            "SELECT state FROM outbox WHERE day=? AND revision=0", (state.day,)
        ).fetchone()[0]
        == "reset_pending"
    )
    with pytest.raises(PortraitPendingError):
        daily.build()
    receipt = publish(store, settings, clock, daily, transport)
    assert receipt.revision == 0
    assert_blank(transport.files[TARGET])
    assert daily.latest() is None  # desired composition remains explicitly pending
    assert daily.state().dog_ids == ("dog-a",)
    assert store.db.execute("SELECT count(*) FROM membership").fetchone()[0] == 2
    assert transport.files["kitchen-tv/unrelated.png"] == b"unchanged"
    store.close()


def test_ready_full_revision_waits_until_reset_verified_then_never_reblanks(tmp_path):
    store, settings, clock, daily, transport = setup(tmp_path)
    dog(store, settings, ready=True)
    daily.record_sighting("dog-a", clock.now())
    full = daily.build()
    reset = daily.latest()
    assert reset.revision == 0 and full.revision == 1
    with pytest.raises(StalePublication, match="reset pending"):
        with daily.publication_guard(full):
            pytest.fail("composition cannot skip the first reset")
    publish(store, settings, clock, daily, transport, reset)
    with pytest.raises(StalePublication):
        with daily.publication_guard(reset):
            pytest.fail("verified reset cannot be retried")
    assert daily.latest().sha256 == full.sha256
    publish(store, settings, clock, daily, transport, full)
    saved = transport.files[TARGET]
    for _ in range(10):
        assert daily.reconcile().dog_ids == ("dog-a",)
        assert daily.latest().sha256 == full.sha256
    assert transport.files[TARGET] == saved
    with pytest.raises(PublishError):
        publish(store, settings, clock, daily, transport, reset)
    assert transport.files[TARGET] == saved
    assert (
        store.db.execute("SELECT count(*) FROM outbox WHERE state='reset_pending'").fetchone()[0]
        == 0
    )
    store.close()


def test_restart_and_smb_outage_keep_reset_priority_until_verified(tmp_path):
    store, settings, clock, daily, transport = setup(tmp_path)
    dog(store, settings)
    daily.record_sighting("dog-a", clock.now())
    daily.reconcile()
    reset = daily.latest()
    previous = transport.files[TARGET]
    transport.fail = True
    with pytest.raises(PublishError):
        publish(store, settings, clock, daily, transport)
    assert transport.files[TARGET] == previous
    path = store.path
    store.close()
    store = Store(path)
    daily = DailyManager(store, settings, clock)
    assert daily.reconcile().dog_ids == ("dog-a",)
    assert daily.latest().sha256 == reset.sha256
    transport.fail = False
    publish(store, settings, clock, daily, transport)
    assert_blank(transport.files[TARGET])
    assert daily.latest() is None
    assert not any(path.endswith(".tmp") for path in transport.files)
    store.close()


def test_legacy_same_day_pending_state_gets_blank_without_membership_changes(tmp_path):
    store, settings, clock, daily, transport = setup(tmp_path)
    dog(store, settings)
    store.db.execute("INSERT INTO days VALUES('2026-10-22','legacy-generation',1,0)")
    store.db.execute("INSERT INTO membership VALUES('2026-10-22','dog-a',0,1)")
    store.db.execute("INSERT INTO meta VALUES('current_day','2026-10-22')")
    before = list(map(tuple, store.db.execute("SELECT * FROM membership")))
    state = daily.reconcile()
    assert state.generation == "legacy-generation" and state.dog_ids == ("dog-a",)
    assert before == list(map(tuple, store.db.execute("SELECT * FROM membership")))
    reset = daily.latest()
    assert reset.revision == 0 and reset.dog_ids == ()
    publish(store, settings, clock, daily, transport)
    assert_blank(transport.files[TARGET])
    assert before == list(map(tuple, store.db.execute("SELECT * FROM membership")))
    store.close()


def test_pending_audit_is_durable_once_per_day_generation_desired_revision(tmp_path):
    store, settings, clock, daily, transport = setup(tmp_path)
    dog(store, settings)
    daily.record_sighting("dog-a", clock.now())
    for _ in range(20):
        assert daily.reconcile().dog_ids == ("dog-a",)
    assert (
        store.db.execute("SELECT count(*) FROM audit WHERE code='composition_pending'").fetchone()[
            0
        ]
        == 1
    )
    path = store.path
    store.close()
    store = Store(path)
    daily = DailyManager(store, settings, clock)
    daily.reconcile()
    assert (
        store.db.execute("SELECT count(*) FROM audit WHERE code='composition_pending'").fetchone()[
            0
        ]
        == 1
    )
    dog(store, settings, "dog-b")
    daily.record_sighting("dog-b", clock.now())
    assert daily.reconcile().dog_ids == ("dog-a", "dog-b")
    assert (
        store.db.execute("SELECT count(*) FROM audit WHERE code='composition_pending'").fetchone()[
            0
        ]
        == 2
    )
    assert daily.latest().dog_ids == ()
    store.close()


def test_old_generation_and_forged_nonblank_reset_are_rejected(tmp_path):
    store, settings, clock, daily, transport = setup(tmp_path)
    daily.reconcile()
    old = daily.latest()
    with pytest.raises(StalePublication):
        with daily.publication_guard(replace(old, dog_ids=("unbound",))):
            pytest.fail("reset exemption requires exact empty record")
    clock.value = datetime(2026, 10, 23, 4, tzinfo=UTC)
    daily.reconcile()
    with pytest.raises(StalePublication):
        with daily.publication_guard(old):
            pytest.fail("yesterday's reset cannot publish")
    assert (
        store.db.execute(
            "SELECT state FROM outbox WHERE day=? AND revision=0", (old.day,)
        ).fetchone()[0]
        == "obsolete"
    )
    current = daily.latest()
    with pytest.raises(StalePublication):
        with daily.publication_guard(
            replace(current, sha256=old.sha256, generation=old.generation)
        ):
            pytest.fail("matching cream hash does not establish current generation")
    publish(store, settings, clock, daily, transport)
    assert_blank(transport.files[TARGET])
    store.close()


def test_existing_full_publication_receipt_prevents_legacy_reset_reintroduction(tmp_path):
    store, settings, clock, daily, transport = setup(tmp_path)
    dog(store, settings, ready=True)
    daily.record_sighting("dog-a", clock.now())
    full = daily.build()
    publish(store, settings, clock, daily, transport)
    publish(store, settings, clock, daily, transport, full)
    store.db.execute("DELETE FROM outbox")  # legacy repair must use verified receipts too
    for _ in range(3):
        daily.reconcile()
        assert daily.latest().sha256 == full.sha256
    assert (
        store.db.execute("SELECT count(*) FROM outbox WHERE state='reset_pending'").fetchone()[0]
        == 0
    )
    assert transport.files[TARGET] == full.output_path.read_bytes()
    store.close()


def test_current_empty_day_retry_is_idempotent_but_cannot_erase_new_members(tmp_path):
    store, settings, clock, daily, transport = setup(tmp_path)
    daily.reconcile()
    blank = daily.latest()
    first = publish(store, settings, clock, daily, transport, blank)
    again = publish(store, settings, clock, daily, transport, blank)
    assert first.sha256 == again.sha256
    assert daily.state().revision == 0
    assert_blank(transport.files[TARGET])
    dog(store, settings, ready=True)
    daily.record_sighting("dog-a", clock.now())
    full = daily.build()
    # The old verified blank is now stale even before full artwork is published.
    with pytest.raises(StalePublication):
        with daily.publication_guard(blank):
            pytest.fail("empty retry cannot bypass later membership")
    publish(store, settings, clock, daily, transport, full)
    dog(store, settings, "dog-b")
    assert daily.record_sighting("dog-b", clock.now())[0].dog_ids == ("dog-a", "dog-b")
    assert daily.reconcile().dog_ids == ("dog-a", "dog-b")
    assert daily.latest() is None
    assert transport.files[TARGET] == full.output_path.read_bytes()
    with pytest.raises(StalePublication):
        with daily.publication_guard(full):
            pytest.fail("older nonblank revision must remain stale")
    with pytest.raises(StalePublication):
        with daily.publication_guard(blank):
            pytest.fail("reset must not clear the previous valid artwork")
    store.close()
