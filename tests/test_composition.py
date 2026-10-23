"""Offline render, persistence, calendar and publication-race evidence."""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from PIL import Image, ImageDraw

from dog_art.clock import FrozenClock
from dog_art.collage import (
    CollageRenderer,
    ImmutableArchiveError,
    LayoutCapacityError,
    load_revision,
)
from dog_art.daily import (
    DailyManager,
    PortraitPendingError,
    PublicationBusyError,
    StalePublication,
    application_lock,
)
from dog_art.publishing import Publisher
from dog_art.safety import sha256
from dog_art.settings import Settings
from dog_art.storage import Store

NOW = datetime(2026, 10, 22, 16, tzinfo=UTC)
ASSETS = Path(__file__).resolve().parents[1] / "assets"
ART = [
    ASSETS / "style/dog-watercolor-transparent.png",
    *sorted((ASSETS / "portraits").glob("*.png")),
]


def settings(root, **extra):
    return Settings(
        {
            "APP_DATA_ROOT": str(root.resolve()),
            "COLLAGE_WIDTH": 1920,
            "COLLAGE_HEIGHT": 1080,
            "COLLAGE_BACKGROUND": "#F3EBDD",
            "COLLAGE_MARGIN_PX": 40,
            "COLLAGE_MIN_DOG_HEIGHT_PX": 120,
            "DAY_TIMEZONE": "America/New_York",
            "MIN_FREE_DISK_MB": 0,
            **extra,
        }
    )


def portrait(path, color=(175, 73, 25, 255), size=(180, 260)):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", size)
    draw = ImageDraw.Draw(image)
    draw.ellipse((30, 15, size[0] - 30, size[1] - 10), fill=color)
    draw.rectangle((38, size[1] - 55, 52, size[1] - 4), fill=color)
    image.save(path)
    return path


def setup_manager(tmp_path, now=NOW):
    root = tmp_path.resolve() / "data"
    store = Store(root / "catalog.sqlite")
    clock = FrozenClock(now)
    manager = DailyManager(store, settings(root), clock)
    return store, clock, manager


def verify_initial_reset(store, clock, manager):
    """Complete real publisher/guard prerequisites before a later-art scenario."""

    class MemorySMB:
        def __init__(self):
            self.files = {}

        def read(self, path):
            if path not in self.files:
                raise FileNotFoundError(path)
            return self.files[path]

        def write_new(self, path, data):
            assert path not in self.files
            self.files[path] = data

        def replace(self, source, target):
            self.files[target] = self.files.pop(source)

        def remove_owned_temp(self, path):
            self.files.pop(path, None)

    cfg = Settings(
        {
            **manager.settings.values,
            "PUBLISH_ENABLED": True,
            "SMB_HOST": "offline.test",
            "SMB_SHARE": "media",
            "SMB_SUBDIRECTORY": "kitchen-tv/dog-art",
            "PUBLISH_FILENAME": "dog-collage.png",
        },
        {"SMB_USERNAME": "offline", "SMB_PASSWORD": "offline"},
    )
    receipt = Publisher(store, cfg, clock, manager, transport=MemorySMB()).publish(manager.latest())
    assert receipt.state == "verified"


def enroll(store, root, name="dog-a", *, ready=True, canonical=None, state="accepted"):
    store.db.execute("INSERT INTO dogs VALUES(?,?,?,?)", (name, NOW.timestamp(), state, canonical))
    path = portrait(root / "portraits" / f"{name}.png")
    if ready:
        store.db.execute(
            "INSERT INTO portraits(recipe_key,dog_id,recipe,state,path,sha256) VALUES(?,?,?,'validated',?,?)",
            (f"recipe-{name}", name, "{}", str(path), sha256(path)),
        )
    return path


def render(tmp_path, count, seed=87, **extra):
    p = portrait(tmp_path / "dog.png")
    return CollageRenderer(settings(tmp_path, **extra)).render(
        {f"dog-{i:03}": p for i in range(count)},
        day="2026-10-22",
        generation="generation-a",
        revision=1,
        seed=seed,
        output_path=tmp_path / f"render-{count}-{seed}.png",
        created_at=NOW,
    )


@pytest.mark.parametrize("count", [0, 1, 5, 30])
def test_render_all_members_exact_opaque_rgb_and_collision_free(tmp_path, count):
    revision = render(tmp_path, count)
    with Image.open(revision.output_path) as image:
        assert image.mode == "RGB"
        assert image.size == (1920, 1080)
        assert image.getpixel((0, 0)) == (243, 235, 221)
        if count == 0:
            assert image.getextrema() == ((243, 243), (235, 235), (221, 221))
    assert len(revision.dog_ids) == len(revision.placements) == count
    assert {p["dog_id"] for p in revision.placements} == set(revision.dog_ids)
    for p in revision.placements:
        assert p["height"] >= 120
        assert p["x"] >= 40 and p["y"] >= 40
        assert p["x"] + p["width"] <= 1880 and p["y"] + p["height"] <= 1040
        source_w = p["source_bbox"][2] - p["source_bbox"][0]
        source_h = p["source_bbox"][3] - p["source_bbox"][1]
        assert abs(p["width"] / p["height"] - source_w / source_h) < 0.012
        for q in revision.placements:
            if p is not q:
                assert (
                    p["x"] + p["width"] <= q["x"]
                    or q["x"] + q["width"] <= p["x"]
                    or p["y"] + p["height"] <= q["y"]
                    or q["y"] + q["height"] <= p["y"]
                )


def test_reproducible_metadata_and_source_colors(tmp_path):
    a = render(tmp_path / "a", 5)
    b = render(tmp_path / "b", 5)
    c = render(tmp_path / "c", 5, seed=99)
    assert a.sha256 == b.sha256
    assert a.placements == b.placements
    assert c.sha256 != a.sha256
    assert load_revision(a.output_path) == a
    with Image.open(a.output_path) as image:
        assert (175, 73, 25) in image.get_flattened_data()
    receipt = json.loads(a.output_path.with_suffix(".json").read_text())
    assert receipt["silhouette_alpha_threshold"] == 16
    assert receipt["portrait_hashes"] == list(a.portrait_hashes)
    with pytest.raises(ImmutableArchiveError):
        CollageRenderer(settings(tmp_path)).render(
            {},
            day=a.day,
            generation=a.generation,
            revision=1,
            seed=87,
            output_path=a.output_path,
            created_at=NOW,
        )


def test_approved_rgba_art_silhouette_bounds_without_source_changes(tmp_path):
    before = {p: sha256(p) for p in ART}
    result = CollageRenderer(settings(tmp_path)).render(
        {f"approved-{i}": p for i, p in enumerate(ART)},
        day="2026-10-22",
        generation="approved",
        revision=1,
        seed=501,
        output_path=tmp_path / "approved.png",
        created_at=NOW,
    )
    assert len(result.placements) == 5
    assert before == {p: sha256(p) for p in ART}
    assert any(tuple(p["source_bbox"]) != (0, 0, *p["source_size"]) for p in result.placements)


def test_capacity_preserves_last_output_and_no_truncation(tmp_path):
    first = render(tmp_path, 1)
    expected = first.output_path.read_bytes()
    with pytest.raises(LayoutCapacityError, match="cannot fit"):
        render(tmp_path, 500)
    assert not (tmp_path / "render-500-87.png").exists()
    assert first.output_path.read_bytes() == expected


def test_daily_repeat_and_reopened_persistence(tmp_path):
    store, clock, manager = setup_manager(tmp_path)
    enroll(store, manager.root)
    blank = manager.reconcile()
    assert blank.revision == 0 and blank.dog_ids == ()
    first = manager.record_sighting("dog-a", NOW)[0]
    built = manager.build()
    clock.value = NOW.replace(hour=17)
    repeat = manager.record_sighting("dog-a", clock.now())[0]
    assert first == repeat
    assert built.revision == 1 and built.dog_ids == ("dog-a",)
    last = store.db.execute("SELECT last_seen FROM membership").fetchone()[0]
    assert last == clock.now().timestamp()
    generation = first.generation
    store.close()
    restored = Store(manager.root / "catalog.sqlite")
    recovered = DailyManager(restored, settings(manager.root), clock)
    assert recovered.reconcile().generation == generation
    assert recovered.build().sha256 == built.sha256
    assert restored.db.execute("SELECT count(*) FROM collages").fetchone()[0] == 2
    restored.close()


def test_missing_portrait_retains_membership_prior_archive_and_blocks_partial(tmp_path):
    store, clock, manager = setup_manager(tmp_path)
    enroll(store, manager.root, ready=False)
    manager.reconcile()
    blank = manager.latest()
    verify_initial_reset(store, clock, manager)
    manager.record_sighting("dog-a", NOW)
    with pytest.raises(PortraitPendingError):
        manager.build()
    assert manager.state().dog_ids == ("dog-a",)
    assert blank.output_path.exists()
    assert manager.latest() is None
    with pytest.raises(StalePublication):
        with manager.publication_guard(blank):
            pytest.fail("old revision must not publish")
    store.close()


def test_merge_canonical_dedup_keeps_historical_bytes(tmp_path):
    store, clock, manager = setup_manager(tmp_path)
    enroll(store, manager.root, "dog-a")
    enroll(store, manager.root, "dog-b")
    manager.reconcile()
    manager.record_sighting("dog-a", NOW)
    manager.record_sighting("dog-b", NOW)
    historical = manager.build()
    original = historical.output_path.read_bytes()
    store.db.execute("UPDATE dogs SET canonical_id='dog-a' WHERE dog_id='dog-b'")
    manager.record_sighting("dog-b", NOW)
    current = manager.build()
    assert current.dog_ids == ("dog-a",)
    assert current.revision > historical.revision
    assert historical.output_path.read_bytes() == original
    assert store.db.execute("SELECT count(*) FROM membership").fetchone()[0] == 1
    store.close()


def test_rollover_once_keeps_catalog_portrait_archives_and_latest_only(tmp_path):
    store, clock, manager = setup_manager(tmp_path)
    p = enroll(store, manager.root)
    manager.reconcile()
    manager.record_sighting("dog-a", NOW)
    old = manager.build()
    expected = p.read_bytes()
    clock.value = datetime(2026, 10, 23, 4, 0, tzinfo=UTC)
    new = manager.reconcile()
    assert new.day == "2026-10-23" and new.dog_ids == () and new.revision == 0
    assert new.generation != old.generation
    assert manager.reconcile() == new
    assert p.read_bytes() == expected and old.output_path.exists()
    assert store.db.execute("SELECT count(*) FROM dogs").fetchone()[0] == 1
    assert (
        store.db.execute("SELECT count(*) FROM audit WHERE code='daily_rollover'").fetchone()[0]
        == 2
    )
    assert [
        r[0]
        for r in store.db.execute(
            "SELECT day FROM outbox WHERE state IN ('pending','reset_pending')"
        )
    ] == [new.day]
    with pytest.raises(StalePublication):
        with manager.publication_guard(old):
            pytest.fail("old-day image cannot publish")
    store.close()


@pytest.mark.parametrize("local_day,hours", [("2026-03-08", 23), ("2026-11-01", 25)])
def test_dst_calendar_days_and_crossed_midnight_observations(tmp_path, local_day, hours):
    zone = ZoneInfo("America/New_York")
    start = datetime.fromisoformat(local_day).replace(tzinfo=zone)
    from datetime import timedelta

    end = start + timedelta(days=1)
    assert (end.astimezone(UTC) - start.astimezone(UTC)).total_seconds() == hours * 3600
    store, clock, manager = setup_manager(tmp_path, end.astimezone(UTC) + timedelta(seconds=10))
    enroll(store, manager.root)
    manager.reconcile()
    before, after = end - timedelta(seconds=1), end + timedelta(seconds=1)
    states = manager.record_sighting("dog-a", [before, after])
    assert [s.day for s in states] == [local_day, end.date().isoformat()]
    assert all(s.dog_ids == ("dog-a",) for s in states)
    old = manager.build(local_day)
    current = manager.build()
    assert old.dog_ids == current.dog_ids
    assert (
        store.db.execute("SELECT count(*) FROM outbox WHERE day=?", (local_day,)).fetchone()[0] == 0
    )
    store.close()


def test_startup_catches_missed_midnights_delayed_portrait_archives_only(tmp_path):
    store, clock, manager = setup_manager(tmp_path)
    enroll(store, manager.root, ready=False)
    manager.reconcile()
    manager.record_sighting("dog-a", NOW)
    old_state = manager.state()
    clock.value = datetime(2026, 10, 25, 16, tzinfo=UTC)
    manager.reconcile()
    current = manager.latest()
    p = manager.root / "portraits/dog-a.png"
    store.db.execute(
        "INSERT INTO portraits(recipe_key,dog_id,recipe,state,path,sha256) VALUES('late','dog-a','{}','validated',?,?)",
        (str(p), sha256(p)),
    )
    old = manager.build(old_state.day)
    assert old.day == "2026-10-22" and old.dog_ids == ("dog-a",)
    assert manager.latest().sha256 == current.sha256
    assert (
        store.db.execute(
            "SELECT count(*) FROM outbox WHERE day=? AND state='pending'", (old.day,)
        ).fetchone()[0]
        == 0
    )
    manager.record_sighting("dog-a", clock.now())
    returned = manager.build()
    assert returned.portrait_hashes == old.portrait_hashes
    assert store.db.execute("SELECT count(*) FROM portraits").fetchone()[0] == 1
    store.close()


def test_midnight_during_upload_revalidation_rejects_and_queues_blank(tmp_path):
    store, clock, manager = setup_manager(tmp_path, datetime(2026, 10, 23, 3, 59, 59, tzinfo=UTC))
    enroll(store, manager.root)
    manager.reconcile()
    verify_initial_reset(store, clock, manager)
    manager.record_sighting("dog-a", clock.now())
    old = manager.build()
    with manager.publication_guard(old) as guard:
        assert not store.db.in_transaction
        clock.value = datetime(2026, 10, 23, 4, 0, tzinfo=UTC)
        with pytest.raises(StalePublication, match="wall date"):
            guard.revalidate()
    assert manager.latest().day == "2026-10-23"
    assert manager.latest().dog_ids == ()
    with pytest.raises(StalePublication):
        guard.revalidate()
    store.close()


def test_second_publisher_and_rollover_wait_on_same_file_barrier(tmp_path):
    store, clock, manager = setup_manager(tmp_path)
    manager.reconcile()
    revision = manager.latest()
    entered, release, attempted = threading.Event(), threading.Event(), threading.Event()
    results, errors = [], []

    def publisher():
        local = Store(store.path)
        try:
            other = DailyManager(local, settings(manager.root), clock)
            attempted.set()
            with other.publication_guard(revision) as guard:
                entered.set()
                guard.revalidate()
                results.append("published")
        except BaseException as error:
            errors.append(error)
        finally:
            local.close()
            release.set()

    with manager.publication_guard(revision):
        thread = threading.Thread(target=publisher)
        thread.start()
        assert attempted.wait(2)
        assert not entered.wait(0.05)
        # The second publisher is already waiting; wall date changed before it
        # can acquire the barrier, so it must reject without replacement.
        clock.value = datetime(2026, 10, 23, 4, tzinfo=UTC)
    assert release.wait(3)
    thread.join()
    assert not results and len(errors) == 1 and isinstance(errors[0], StalePublication)
    assert manager.latest().dog_ids == ()
    store.close()


def test_lock_wait_is_bounded_and_no_network_database_transaction(tmp_path):
    path = tmp_path / "publication.lock"
    failures = []
    with application_lock(path):

        def contender():
            try:
                with application_lock(path, timeout=0.03):
                    failures.append("unexpected lock")
            except PublicationBusyError:
                failures.append("bounded")

        thread = threading.Thread(target=contender)
        thread.start()
        thread.join(1)
    assert failures == ["bounded"]


def test_reject_uncertain_future_and_naive_timestamps(tmp_path):
    store, clock, manager = setup_manager(tmp_path)
    enroll(store, manager.root, "uncertain", state="candidate")
    with pytest.raises(ValueError, match="accepted"):
        manager.record_sighting("uncertain", NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        manager.record_sighting("uncertain", NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="future-date"):
        manager.record_sighting("uncertain", datetime(2026, 10, 24, tzinfo=UTC))
    store.close()


def test_incomplete_receipt_after_crash_recovered_without_archive_rewrite(tmp_path):
    store, clock, manager = setup_manager(tmp_path)
    manager.reconcile()
    first = manager.latest()
    original = first.output_path.read_bytes()
    first.output_path.with_suffix(".json").unlink()
    store.db.execute("DELETE FROM outbox")
    store.db.execute("DELETE FROM collages")
    manager.reconcile()
    recovered = manager.latest()
    assert recovered.sha256 == first.sha256
    assert first.output_path.read_bytes() == original
    assert (
        store.db.execute(
            "SELECT count(*) FROM audit WHERE code='archive_receipt_recovered'"
        ).fetchone()[0]
        == 1
    )
    store.close()


def test_low_disk_retains_members_and_last_valid_archive(tmp_path, monkeypatch):
    import dog_art.daily as daily
    from dog_art.safety import SafetyError

    store, clock, manager = setup_manager(tmp_path)
    manager.reconcile()
    original = manager.latest()
    enroll(store, manager.root)
    manager.record_sighting("dog-a", NOW)

    def low_disk(*args):
        raise SafetyError("low disk: preserve retained data and last valid output")

    monkeypatch.setattr(daily, "disk_guard", low_disk)
    with pytest.raises(SafetyError, match="low disk"):
        manager.build()
    assert manager.state().dog_ids == ("dog-a",)
    assert sha256(original.output_path) == original.sha256
    assert store.db.execute("SELECT count(*) FROM collages").fetchone()[0] == 1
    store.close()
