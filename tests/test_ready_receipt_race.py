"""Readiness/date changes at receipt creation cannot commit stale verification."""

import json
from datetime import timedelta

import pytest
from test_ready_collages import approve, ready_setup
from test_reset_priority import TARGET, assert_blank, publish

import dog_art.publishing as publishing
from dog_art.publishing import PublishError


def receipt_count(store, revision):
    return store.db.execute(
        "SELECT count(*) FROM publications WHERE json_extract(payload,'$.generation')=? "
        "AND json_extract(payload,'$.revision')=?",
        (revision.generation, revision.revision),
    ).fetchone()[0]


def test_approval_after_readback_cannot_commit_old_partial_receipt(tmp_path, monkeypatch):
    store, settings, clock, daily, transport = ready_setup(tmp_path, count=3, ready=1)
    try:
        partial = daily.build()
        publish(store, settings, clock, daily, transport)  # Verify the priority reset first.
        members = list(map(tuple, store.db.execute("SELECT * FROM membership ORDER BY dog_id")))
        requests = list(map(tuple, store.db.execute("SELECT * FROM requests")))
        original = publishing.PublishReceipt
        injected = False

        def approve_after_final_readback(*args, **kwargs):
            nonlocal injected
            receipt = original(*args, **kwargs)
            assert receipt.revision == partial.revision
            assert transport.files[TARGET] == partial.output_path.read_bytes()
            approve(store, settings, "dog-1")
            injected = True
            return receipt

        with monkeypatch.context() as patch:
            patch.setattr(publishing, "PublishReceipt", approve_after_final_readback)
            with pytest.raises(PublishError):
                publish(store, settings, clock, daily, transport, partial)

        assert injected and receipt_count(store, partial) == 0
        assert (
            store.db.execute(
                "SELECT state FROM outbox WHERE day=? AND revision=?",
                (partial.day, partial.revision),
            ).fetchone()[0]
            != "published"
        )
        assert members == list(
            map(tuple, store.db.execute("SELECT * FROM membership ORDER BY dog_id"))
        )
        assert requests == list(map(tuple, store.db.execute("SELECT * FROM requests")))
        state = daily.state()
        assert state.revision > partial.revision and len(state.dog_ids) == 3
        current = daily.build()
        assert current.dog_ids == ("dog-0", "dog-1")
        assert current.pending_dog_ids == ("dog-2",)
        publish(store, settings, clock, daily, transport, current)
        assert receipt_count(store, current) == 1
        assert receipt_count(store, partial) == 0
    finally:
        store.close()


def test_midnight_after_readback_cannot_commit_old_day_receipt(tmp_path, monkeypatch):
    store, settings, clock, daily, transport = ready_setup(tmp_path, count=2, ready=1)
    try:
        partial = daily.build()
        publish(store, settings, clock, daily, transport)
        original = publishing.PublishReceipt
        injected = False

        def midnight_after_final_readback(*args, **kwargs):
            nonlocal injected
            receipt = original(*args, **kwargs)
            assert receipt.revision == partial.revision
            clock.value += timedelta(days=1)
            injected = True
            return receipt

        with monkeypatch.context() as patch:
            patch.setattr(publishing, "PublishReceipt", midnight_after_final_readback)
            with pytest.raises(PublishError):
                publish(store, settings, clock, daily, transport, partial)

        assert injected and receipt_count(store, partial) == 0
        new_day = daily.reconcile()
        assert new_day.day != partial.day and new_day.dog_ids == ()
        reset = daily.latest()
        assert reset.day == new_day.day and reset.revision == 0
        assert reset.pending_dog_ids == ()
        publish(store, settings, clock, daily, transport, reset)
        assert_blank(transport.files[TARGET])
        assert (
            store.db.execute(
                "SELECT count(*) FROM membership WHERE day=?", (partial.day,)
            ).fetchone()[0]
            == 2
        )
        assert all(
            json.loads(row[0])["generation"] != partial.generation
            or json.loads(row[0])["revision"] != partial.revision
            for row in store.db.execute("SELECT payload FROM publications")
        )
    finally:
        store.close()
