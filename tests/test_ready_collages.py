"""User-authorized approved-only display, retaining every accepted membership."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from test_reset_priority import TARGET, assert_blank, dog, publish, setup

from dog_art.collage import load_revision
from dog_art.daily import DailyManager, PortraitPendingError, StalePublication
from dog_art.publishing import PublishError
from dog_art.safety import sha256
from dog_art.storage import Store


def ready_setup(tmp_path, policy="approved_only", count=8, ready=5):
    store, settings, clock, _, transport = setup(tmp_path)
    settings = replace(settings, values={**settings.values, "COLLAGE_PORTRAIT_POLICY": policy})
    daily = DailyManager(store, settings, clock)
    for number in range(count):
        name = f"dog-{number}"
        dog(store, settings, name, ready=number < ready)
        daily.record_sighting(name, clock.now())
    return store, settings, clock, daily, transport


def approve(store, settings, name):
    path = Path(settings["APP_DATA_ROOT"]) / "portraits" / f"{name}-approved.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (512, 512))
    ImageDraw.Draw(image).ellipse((50, 50, 460, 460), fill=(100, 50, 25, 255))
    image.save(path)
    existing = store.db.execute(
        "SELECT recipe_key FROM portraits WHERE dog_id=? AND state='needs_review' LIMIT 1", (name,)
    ).fetchone()
    if existing:
        store.db.execute(
            "UPDATE portraits SET state='validated',path=?,sha256=? WHERE recipe_key=?",
            (str(path), sha256(path), existing[0]),
        )
        store.db.execute("UPDATE requests SET state='validated' WHERE recipe_key=?", (existing[0],))
    else:
        store.db.execute(
            "INSERT INTO portraits(recipe_key,dog_id,recipe,state,path,sha256) VALUES(?,?,'{}','validated',?,?)",
            ("approval-" + name, name, str(path), sha256(path)),
        )
    return path


def test_five_of_eight_publishes_then_six_without_new_sighting_and_keeps_budget_holds(tmp_path):
    store, settings, clock, daily, transport = ready_setup(tmp_path)
    # Both pending visual review and a budget-held observation stay members.
    store.db.execute(
        "INSERT INTO portraits(recipe_key,dog_id,recipe,state) VALUES('review-5','dog-5','{}','needs_review')"
    )
    store.db.execute(
        "INSERT INTO portraits(recipe_key,dog_id,recipe,state) VALUES('review-6','dog-6','{}','needs_review')"
    )
    # Existing reservations total $5; the eighth entry is waiting before any
    # paid reservation. Composition must neither reserve nor resume this job.
    for number in range(7):
        recipe = f"recipe-dog-{number}" if number < 5 else f"review-{number}"
        store.db.execute(
            "INSERT INTO requests(request_id,recipe_key,day,reserved_usd,state,created_at) VALUES(?,?,'2026-10-22',?,?,0)",
            (
                f"paid-{number}",
                recipe,
                0.8 if number < 5 else 0.5,
                "validated" if number < 5 else "needs_review",
            ),
        )
    store.enqueue("portrait", "held-dog-7", {"dog_id": "dog-7"}, clock.now().timestamp())
    store.db.execute(
        "UPDATE jobs SET state='dependency_wait',error_code='PortraitBudgetWait' WHERE dedup_key='held-dog-7'"
    )
    budget_before = tuple(
        store.db.execute("SELECT * FROM jobs WHERE dedup_key='held-dog-7'").fetchone()
    )
    before = list(map(tuple, store.db.execute("SELECT * FROM membership ORDER BY dog_id")))
    paid_before = list(
        map(
            tuple,
            store.db.execute(
                "SELECT request_id,recipe_key,day,reserved_usd,created_at FROM requests ORDER BY request_id"
            ),
        )
    )
    five = daily.build()
    assert len(five.dog_ids) == 5 and five.pending_dog_ids == ("dog-5", "dog-6", "dog-7")
    assert five.portrait_policy == "approved_only"
    assert len(daily.state().dog_ids) == 8
    publish(store, settings, clock, daily, transport)  # reset first
    publish(store, settings, clock, daily, transport, five)
    assert transport.files[TARGET] == five.output_path.read_bytes()
    approve(store, settings, "dog-5")
    assert daily.latest() is None  # approval alone invalidates old desired output
    with pytest.raises(StalePublication):
        with daily.publication_guard(five):
            pytest.fail("old approval subset must never republish")
    six = daily.build()
    assert len(six.dog_ids) == 6 and six.revision > five.revision
    assert six.pending_dog_ids == ("dog-6", "dog-7")
    publish(store, settings, clock, daily, transport, six)
    assert transport.files[TARGET] == six.output_path.read_bytes()
    assert before == list(map(tuple, store.db.execute("SELECT * FROM membership ORDER BY dog_id")))
    assert paid_before == list(
        map(
            tuple,
            store.db.execute(
                "SELECT request_id,recipe_key,day,reserved_usd,created_at FROM requests ORDER BY request_id"
            ),
        )
    )
    assert store.db.execute("SELECT sum(reserved_usd) FROM requests").fetchone()[0] == 5
    assert budget_before == tuple(
        store.db.execute("SELECT * FROM jobs WHERE dedup_key='held-dog-7'").fetchone()
    )
    assert load_revision(five.output_path) == five
    store.close()


def test_partial_revision_restart_is_idempotent_and_receipts_retain_pending_metadata(tmp_path):
    store, settings, clock, daily, transport = ready_setup(tmp_path)
    first = daily.build()
    receipt = json.loads(first.output_path.with_suffix(".json").read_text())
    assert receipt["pending_dog_ids"] == list(first.pending_dog_ids)
    state = daily.state()
    database = store.path
    store.close()
    store = Store(database)
    daily = DailyManager(store, settings, clock)
    assert daily.reconcile() == state
    again = daily.build()
    assert again == first and load_revision(first.output_path) == first
    assert len(daily.state().dog_ids) == 8
    store.close()


def test_no_ready_portraits_is_cream_with_explicit_pending_and_strict_default_still_holds(tmp_path):
    store, settings, clock, daily, transport = ready_setup(tmp_path, count=3, ready=0)
    revision = daily.build()
    assert revision.dog_ids == () and revision.pending_dog_ids == ("dog-0", "dog-1", "dog-2")
    assert len(daily.state().dog_ids) == 3
    publish(store, settings, clock, daily, transport)
    publish(store, settings, clock, daily, transport, revision)
    assert_blank(transport.files[TARGET])
    strict_settings = replace(
        settings,
        values={k: v for k, v in settings.values.items() if k != "COLLAGE_PORTRAIT_POLICY"},
    )
    strict = DailyManager(store, strict_settings, clock)
    with pytest.raises(PortraitPendingError):
        strict.build()
    assert strict.state().dog_ids == daily.state().dog_ids
    store.close()


@pytest.mark.parametrize("problem", ["missing", "changed", "missing_metadata", "symlink"])
def test_bad_validated_art_is_technical_hold_and_never_silently_skipped(tmp_path, problem):
    store, settings, clock, daily, transport = ready_setup(tmp_path, count=2, ready=1)
    good = daily.build()
    row = store.db.execute("SELECT path FROM portraits WHERE state='validated'").fetchone()
    path = Path(row[0])
    if problem == "missing":
        path.unlink()
    elif problem == "changed":
        path.write_bytes(b"corrupt approved bytes")
    elif problem == "missing_metadata":
        store.db.execute("UPDATE portraits SET path=NULL WHERE state='validated'")
    else:
        other = path.with_suffix(".original")
        path.rename(other)
        path.symlink_to(other)
    with pytest.raises((PortraitPendingError, ValueError)):
        daily.build()
    assert len(daily.state().dog_ids) == 2
    assert good.output_path.exists()
    assert store.db.execute("SELECT count(*) FROM membership").fetchone()[0] == 2
    store.close()


def test_approval_during_render_preserves_prior_bytes_and_rejects_stale_composition(
    tmp_path, monkeypatch
):
    store, settings, clock, daily, transport = ready_setup(tmp_path, count=2, ready=1)
    real = daily.renderer.render
    changed = False

    def race(*args, **kwargs):
        nonlocal changed
        result = real(*args, **kwargs)
        if kwargs["revision"] > 0 and not changed:
            changed = True
            approve(store, settings, "dog-1")
        return result

    monkeypatch.setattr(daily.renderer, "render", race)
    with pytest.raises(StalePublication):
        daily.build()
    monkeypatch.setattr(daily.renderer, "render", real)
    current = daily.build()
    assert current.dog_ids == ("dog-0", "dog-1") and current.pending_dog_ids == ()
    assert len(daily.state().dog_ids) == 2
    store.close()


def test_approval_during_upload_rechecks_without_build_and_never_replaces_old_target(tmp_path):
    store, settings, clock, daily, transport = ready_setup(tmp_path, count=2, ready=1)
    partial = daily.build()
    publish(store, settings, clock, daily, transport)
    before = transport.files[TARGET]
    real = transport.write_new

    def upload_and_approve(path, data):
        real(path, data)
        approve(store, settings, "dog-1")

    transport.write_new = upload_and_approve
    with pytest.raises(PublishError):
        publish(store, settings, clock, daily, transport, partial)
    assert transport.files[TARGET] == before
    assert daily.state().revision > partial.revision
    store.close()


def test_midnight_rejects_old_partial_and_new_generation_reset_is_first(tmp_path):
    store, settings, clock, daily, transport = ready_setup(tmp_path, count=2, ready=1)
    partial = daily.build()
    publish(store, settings, clock, daily, transport)
    publish(store, settings, clock, daily, transport, partial)
    clock.value = datetime(2026, 10, 23, 4, tzinfo=UTC)
    daily.record_sighting("dog-0", clock.now())
    daily.record_sighting("dog-1", clock.now())
    new = daily.build()
    assert new.day != partial.day
    assert daily.latest().revision == 0
    with pytest.raises(StalePublication):
        with daily.publication_guard(partial):
            pytest.fail("old partial cannot replace a new day's reset")
    publish(store, settings, clock, daily, transport)
    assert_blank(transport.files[TARGET])
    publish(store, settings, clock, daily, transport, new)
    assert len(daily.state().dog_ids) == 2
    store.close()


def test_policy_switch_and_legacy_receipt_preserve_original_revision_bytes(tmp_path):
    store, settings, clock, strict, transport = ready_setup(
        tmp_path, policy="all_accepted", count=2, ready=2
    )
    old = strict.build()
    original = old.output_path.read_bytes()
    # Remove additive metadata, reproducing an already delivered legacy receipt.
    metadata = json.loads(old.output_path.with_suffix(".json").read_text())
    metadata.pop("pending_dog_ids")
    metadata.pop("portrait_policy")
    old.output_path.with_suffix(".json").write_text(json.dumps(metadata))
    assert load_revision(old.output_path).pending_dog_ids == ()
    assert load_revision(old.output_path).portrait_policy == "all_accepted"
    store.db.execute("DELETE FROM meta WHERE key LIKE 'collage_inputs:%'")
    approved_settings = replace(
        settings, values={**settings.values, "COLLAGE_PORTRAIT_POLICY": "approved_only"}
    )
    approved = DailyManager(store, approved_settings, clock)
    current = approved.build()
    assert current.revision > old.revision and current.portrait_policy == "approved_only"
    assert old.output_path.read_bytes() == original
    switched_back = DailyManager(store, settings, clock).build()
    assert switched_back.revision > current.revision
    assert switched_back.portrait_policy == "all_accepted"
    store.close()


def test_changed_validated_hash_creates_new_revision_and_rejects_old_publication(tmp_path):
    store, settings, clock, daily, transport = ready_setup(tmp_path, count=1, ready=1)
    old = daily.build()
    publish(store, settings, clock, daily, transport)
    publish(store, settings, clock, daily, transport, old)
    path = Path(
        store.db.execute("SELECT path FROM portraits WHERE state='validated'").fetchone()[0]
    )
    image = Image.new("RGBA", (512, 512))
    ImageDraw.Draw(image).ellipse((50, 50, 460, 460), fill=(30, 60, 120, 255))
    image.save(path)
    store.db.execute("UPDATE portraits SET sha256=? WHERE state='validated'", (sha256(path),))
    with pytest.raises(StalePublication):
        with daily.publication_guard(old):
            pytest.fail("changed approved bytes cannot republish old layout")
    new = daily.build()
    assert new.revision > old.revision and new.sha256 != old.sha256
    store.close()


def test_receipt_crash_recovery_preserves_partial_metadata_and_exact_pixels(tmp_path):
    store, settings, clock, daily, transport = ready_setup(tmp_path, count=3, ready=1)
    first = daily.build()
    first.output_path.with_suffix(".json").unlink()
    store.db.execute("DELETE FROM collages WHERE day=? AND revision=?", (first.day, first.revision))
    recovered = daily.build()
    assert recovered.sha256 == first.sha256
    assert recovered.pending_dog_ids == first.pending_dog_ids
    assert recovered.portrait_policy == "approved_only"
    assert load_revision(recovered.output_path) == recovered
    store.close()


def test_new_pending_member_and_forged_metadata_reject_old_partial_without_build(tmp_path):
    store, settings, clock, daily, transport = ready_setup(tmp_path, count=2, ready=1)
    partial = daily.build()
    publish(store, settings, clock, daily, transport)
    publish(store, settings, clock, daily, transport, partial)
    for forged in [
        replace(partial, pending_dog_ids=()),
        replace(partial, portrait_policy="all_accepted"),
    ]:
        with pytest.raises(StalePublication):
            with daily.publication_guard(forged):
                pytest.fail("receipt metadata must agree with the selected policy")
    dog(store, settings, "dog-2")
    daily.record_sighting("dog-2", clock.now())
    with pytest.raises(StalePublication):
        with daily.publication_guard(partial):
            pytest.fail("new pending membership must invalidate the old receipt")
    current = daily.build()
    assert current.dog_ids == partial.dog_ids
    assert current.pending_dog_ids == ("dog-1", "dog-2")
    assert current.revision > partial.revision
    assert len(daily.state().dog_ids) == 3
    store.close()


def test_receipt_transaction_guard_reuses_supplied_database_without_rollover_or_render(
    tmp_path, monkeypatch
):
    store, settings, clock, daily, transport = ready_setup(tmp_path, count=2, ready=1)
    partial = daily.build()
    publish(store, settings, clock, daily, transport)
    with daily.publication_guard(partial) as guard:

        def forbidden(*args, **kwargs):
            pytest.fail("receipt guard must not open rollover/render work")

        monkeypatch.setattr(daily, "_rollover_locked", forbidden)
        monkeypatch.setattr(daily.renderer, "render", forbidden)
        with store.transaction() as db:
            assert guard.revalidate(db=db) == partial
            assert db.in_transaction
    store.close()


def test_layout_setting_change_uses_fresh_revision_and_retains_old_bytes(tmp_path):
    store, settings, clock, daily, transport = ready_setup(tmp_path, count=2, ready=1)
    old = daily.build()
    original = old.output_path.read_bytes()
    settings = replace(settings, values={**settings.values, "COLLAGE_BACKGROUND": "#EEE4D4"})
    changed = DailyManager(store, settings, clock).build()
    assert changed.revision > old.revision
    assert changed.background == "#EEE4D4" and changed.sha256 != old.sha256
    assert old.output_path.read_bytes() == original
    assert changed.pending_dog_ids == old.pending_dog_ids
    store.close()
