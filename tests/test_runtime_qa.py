"""Durable saved-output review; fake transports do not establish art quality."""

import base64
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from dog_art.budget import BudgetError
from dog_art.clock import FrozenClock
from dog_art.contracts import CropRef, DogDescription, DogObservation
from dog_art.frigate import EventIngestor
from dog_art.portraits import PortraitService
from dog_art.portraits.review import QA_POLICY_VERSION, QA_PROMPT_SHA256
from dog_art.runtime import Pipeline
from dog_art.safety import fingerprint, sha256
from dog_art.settings import Settings, load_settings

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 22, 12, tzinfo=UTC)


class Reviewer:
    def __init__(self, settings, *, decision="pass", spoof=None):
        self.settings = settings
        self.calls = 0
        self.decision = decision
        self.spoof = spoof

    def review(self, path, digest, description):
        self.calls += 1
        result = {
            "decision": self.decision,
            "image_sha256": digest,
            "description_sha256": fingerprint(asdict(description)),
            "style_sha256": sha256(
                Path(str(files("dog_art").joinpath("resources/dog-watercolor-transparent.png")))
            ),
            "model": self.settings["OLLAMA_MODEL"],
            "digest": self.settings["OLLAMA_MODEL_DIGEST"],
            "policy_version": QA_POLICY_VERSION,
            "prompt_sha256": QA_PROMPT_SHA256,
            "source_reference_policy": self.settings["SOURCE_REFERENCE_POLICY"],
            "evidence": {
                "input_provenance": "generated_artwork",
                "model_verified_before_and_after": True,
                "checks": dict.fromkeys(
                    (
                        "one_dog",
                        "complete_anatomy",
                        "no_extras",
                        "style_matches",
                        "confirmed_facts_match",
                        "clean_exterior",
                    ),
                    True,
                ),
                "reasons": [],
            },
        }
        if self.spoof:
            result[self.spoof] = "spoofed"
        return result


def seeded(tmp_path, *, saved=True, decision="pass", spoof=None):
    raw = load_settings(ROOT / "config/app.toml", tmp_path / ".env", environ={})
    cfg = Settings(
        {
            **raw.values,
            "APP_DATA_ROOT": str(tmp_path / "state"),
            "OPENAI_GENERATION_ENABLED": True,
            "PUBLISH_ENABLED": False,
            "MIN_FREE_DISK_MB": 0,
            "LOCAL_IMAGE_ENCODER": "",
            "LOCAL_DOG_DETECTOR": "",
        },
        {"OPENAI_API_KEY": "test-only"},
    )
    reviewer = Reviewer(cfg, decision=decision, spoof=spoof)
    pipe = Pipeline(cfg, mode="live", clock=FrozenClock(NOW), portrait_reviewer=reviewer)
    EventIngestor(pipe.store, cfg, pipe.clock).record(
        {
            "id": "event",
            "camera": "driveway_ptz",
            "label": "dog",
            "start_time": NOW.timestamp(),
            "end_time": NOW.timestamp() + 1,
            "false_positive": False,
            "has_snapshot": True,
        }
    )
    path = pipe.root / "source.png"
    Image.new("RGB", (64, 64), "black").save(path)
    crop = CropRef(path, sha256(path), NOW, (0, 0, 64, 64), (64, 64), 1, False)
    obs = DogObservation("observation", "event", "track", "driveway_ptz", NOW, (crop,), 1)
    pipe._persist_observations((obs,))
    facts = DogDescription(coat_colors=("black",))
    pipe.store.db.execute("INSERT INTO dogs VALUES('dog',?,'accepted',NULL)", (NOW.timestamp(),))
    pipe.store.db.execute("UPDATE observations SET dog_id='dog',state='accepted'")
    pipe.store.db.execute(
        "INSERT INTO descriptions VALUES(?,?,?,?)",
        ("observation", cfg["OLLAMA_MODEL"], cfg["OLLAMA_MODEL_DIGEST"], json.dumps(asdict(facts))),
    )
    pipe.daily.record_sighting("dog", [NOW])
    calls = []

    def edit(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            data=[
                SimpleNamespace(
                    b64_json=base64.b64encode(
                        (ROOT / "assets/style/dog-watercolor-transparent.png").read_bytes()
                    ).decode()
                )
            ],
            usage=None,
            _request_id="fake",
        )

    service = PortraitService(
        pipe.store, cfg, pipe.clock, client=SimpleNamespace(images=SimpleNamespace(edit=edit))
    )
    if saved:
        service.generate("dog", facts, reserve_usd=0.5)
    pipe.store.db.execute("UPDATE jobs SET state='done'")
    return pipe, reviewer, calls, service, facts


def test_saved_output_recovery_autoaccept_wakes_collage_without_paid_retry(tmp_path):
    pipe, reviewer, calls, _, _ = seeded(tmp_path)
    pipe._queue_portrait_reviews()
    pipe._queue_portrait_reviews()
    assert (
        pipe.store.db.execute("SELECT count(*) FROM jobs WHERE kind='portrait_review'").fetchone()[
            0
        ]
        == 1
    )
    assert pipe.work_once()
    assert reviewer.calls == 1 and len(calls) == 1
    assert pipe.store.status()["requests"] == {"validated": 1}
    assert pipe.store.db.execute("SELECT state FROM portraits").fetchone()[0] == "validated"
    assert pipe.daily.build().dog_ids == ("dog",)
    pipe._queue_portrait_reviews()
    assert reviewer.calls == 1
    pipe.close()


def test_negative_saved_output_stays_review_without_repeated_local_or_paid_calls(tmp_path):
    pipe, reviewer, calls, _, _ = seeded(tmp_path, decision="needs_review")
    pipe._queue_portrait_reviews()
    pipe.work_once()
    pipe._queue_portrait_reviews()
    assert pipe.store.status()["requests"] == {"needs_review": 1}
    assert reviewer.calls == 1 and len(calls) == 1
    assert (
        pipe.store.db.execute("SELECT state FROM jobs WHERE kind='portrait_review'").fetchone()[0]
        == "done"
    )
    pipe.close()


@pytest.mark.parametrize(
    "spoof",
    [
        "image_sha256",
        "description_sha256",
        "style_sha256",
        "model",
        "digest",
        "policy_version",
        "prompt_sha256",
        "source_reference_policy",
    ],
)
def test_passing_report_cannot_validate_different_provenance(tmp_path, spoof):
    pipe, reviewer, _, _, _ = seeded(tmp_path, spoof=spoof)
    pipe._queue_portrait_reviews()
    pipe.work_once()
    assert pipe.store.status()["requests"] == {"needs_review": 1}
    assert (
        pipe.store.db.execute(
            "SELECT count(*) FROM audit WHERE code='portrait_validated'"
        ).fetchone()[0]
        == 0
    )
    pipe.close()


def test_policy_change_invalidates_queued_review_and_schedules_fresh_key(tmp_path):
    pipe, reviewer, _, _, _ = seeded(tmp_path)
    pipe._queue_portrait_reviews()
    pipe.settings = Settings(
        {**pipe.settings.values, "OLLAMA_MODEL_DIGEST": "b" * 64}, pipe.settings.secrets
    )
    pipe.work_once()
    pipe._queue_portrait_reviews()
    assert reviewer.calls == 0
    assert pipe.store.status()["requests"] == {"needs_review": 1}
    assert (
        pipe.store.db.execute("SELECT count(*) FROM jobs WHERE kind='portrait_review'").fetchone()[
            0
        ]
        == 2
    )
    pipe.close()


def test_saved_output_recovered_after_process_restart(tmp_path):
    pipe, _, _, _, _ = seeded(tmp_path)
    cfg = pipe.settings
    pipe.close()
    replacement = Pipeline(
        cfg, mode="live", clock=FrozenClock(NOW), portrait_reviewer=Reviewer(cfg)
    )
    replacement.tick(reconcile_source=False, max_jobs=0)
    assert (
        replacement.store.db.execute(
            "SELECT state FROM jobs WHERE kind='portrait_review'"
        ).fetchone()[0]
        == "queued"
    )
    replacement.close()


def test_shadow_does_not_automatically_review_or_generate(tmp_path):
    pipe, reviewer, calls, _, _ = seeded(tmp_path)
    pipe.mode = "shadow"
    pipe._queue_missing_portraits()
    pipe._queue_portrait_reviews()
    assert (
        pipe.store.db.execute("SELECT count(*) FROM jobs WHERE kind='portrait_review'").fetchone()[
            0
        ]
        == 0
    )
    assert reviewer.calls == 0 and len(calls) == 1
    pipe.close()


def test_budget_rejection_before_reservation_waits_until_next_day_without_paid_attempt(
    tmp_path, monkeypatch
):
    pipe, _, calls, service, facts = seeded(tmp_path, saved=False)
    original = PortraitService.generate

    def unavailable(*a, **k):
        raise BudgetError("daily limit reached")

    monkeypatch.setattr(PortraitService, "generate", unavailable)
    pipe._queue_missing_portraits()
    pipe.work_once()
    row = pipe.store.db.execute("SELECT state,attempts FROM jobs WHERE kind='portrait'").fetchone()
    assert tuple(row) == ("dependency_wait", 0)
    assert not pipe.store.status()["requests"] and calls == []
    pipe._resume_portrait_budget()
    assert (
        pipe.store.db.execute("SELECT state FROM jobs WHERE kind='portrait'").fetchone()[0]
        == "dependency_wait"
    )
    pipe.clock.value += timedelta(days=1)
    pipe._resume_portrait_budget()
    assert (
        pipe.store.db.execute("SELECT state FROM jobs WHERE kind='portrait'").fetchone()[0]
        == "queued"
    )

    monkeypatch.setattr(PortraitService, "generate", original)
    # Use the existing fake transport, retaining the real request ledger.
    monkeypatch.setattr(
        PortraitService, "generate", lambda self, *a, **k: original(service, *a, **k)
    )
    pipe.work_once()
    assert len(calls) == 1 and pipe.store.status()["requests"] == {"needs_review": 1}
    assert pipe.store.db.execute("SELECT reserved_usd FROM requests").fetchone()[0] == 0.5
    pipe.close()


@pytest.mark.parametrize("mutation", ["assignment", "description", "canonical", "recipe"])
def test_source_correction_during_review_cannot_validate_stale_report(tmp_path, mutation):
    from dog_art.storage import Store

    pipe, reviewer, calls, _, _ = seeded(tmp_path)
    original = reviewer.review

    def changed(path, digest, facts):
        report = original(path, digest, facts)
        other = Store(pipe.store.path)
        try:
            other.db.execute(
                "INSERT INTO dogs VALUES('other',?,'accepted',NULL)", (NOW.timestamp(),)
            )
            if mutation == "assignment":
                other.db.execute("UPDATE observations SET dog_id='other'")
            elif mutation == "description":
                other.db.execute(
                    "UPDATE descriptions SET payload=?",
                    (json.dumps(asdict(DogDescription(coat_colors=("brown",)))),),
                )
            elif mutation == "canonical":
                other.db.execute("UPDATE dogs SET canonical_id='other' WHERE dog_id='dog'")
            else:
                other.db.execute("UPDATE portraits SET recipe='{}'")
        finally:
            other.close()
        return report

    reviewer.review = changed
    pipe._queue_portrait_reviews()
    pipe.work_once()
    assert pipe.store.status()["requests"] == {"needs_review": 1}
    assert len(calls) == 1 and reviewer.calls == 1
    assert (
        pipe.store.db.execute(
            "SELECT count(*) FROM audit WHERE code='portrait_validated'"
        ).fetchone()[0]
        == 0
    )
    pipe.close()


def test_transient_local_review_retries_only_saved_artwork_with_finite_attempts(tmp_path):
    pipe, reviewer, calls, _, _ = seeded(tmp_path)
    original = reviewer.review
    count = 0

    def flaky(path, digest, facts):
        nonlocal count
        count += 1
        if count == 1:
            return {
                "decision": "needs_review",
                "retryable": True,
                "review_status": "technical_failure",
            }
        return original(path, digest, facts)

    reviewer.review = flaky
    pipe._queue_portrait_reviews()
    pipe.work_once()
    assert pipe.store.status()["requests"] == {"needs_review": 1}
    job = pipe.store.db.execute("SELECT * FROM jobs WHERE kind='portrait_review'").fetchone()
    assert job["state"] == "queued" and job["attempts"] == 1
    pipe.clock.value += timedelta(seconds=pipe.settings["RETRY_MAX_SECONDS"] + 1)
    pipe.work_once()
    assert pipe.store.status()["requests"] == {"validated": 1}
    assert count == 2 and len(calls) == 1
    pipe.close()


def test_persistent_local_review_outage_exhausts_finite_read_attempts(tmp_path):
    pipe, reviewer, calls, _, _ = seeded(tmp_path)
    attempts = []

    def unavailable(*args):
        attempts.append(1)
        return {"decision": "needs_review", "retryable": True}

    reviewer.review = unavailable
    pipe._queue_portrait_reviews()
    for _ in range(pipe.settings["READ_RETRY_ATTEMPTS"] + 2):
        pipe.work_once()
        pipe.clock.value += timedelta(seconds=pipe.settings["RETRY_MAX_SECONDS"] + 1)
        pipe._queue_portrait_reviews()
    row = pipe.store.db.execute("SELECT * FROM jobs WHERE kind='portrait_review'").fetchone()
    assert row["state"] == "exhausted"
    assert len(attempts) == pipe.settings["READ_RETRY_ATTEMPTS"]
    assert len(calls) == 1 and pipe.store.status()["requests"] == {"needs_review": 1}
    pipe.close()


def test_real_rollover_cli_reports_pending_composition_without_failed_calendar_or_paid_retry(
    tmp_path, monkeypatch, capsys
):
    import dog_art.runtime as runtime
    from dog_art.cli import main
    from dog_art.storage import Store

    pipe, _, calls, _, _ = seeded(tmp_path)
    values = {**pipe.settings.values, "OPENAI_GENERATION_ENABLED": False, "PUBLISH_ENABLED": False}
    database = pipe.store.path
    pipe.close()
    app = tmp_path / "reset-app.toml"
    app.write_text("\n".join(k + " = " + json.dumps(v) for k, v in values.items()) + "\n")
    secrets = tmp_path / "reset.env"
    secrets.write_text("")
    monkeypatch.setattr(runtime, "Clock", lambda: FrozenClock(NOW))
    result = main(["--config", str(app), "--secrets-file", str(secrets), "rollover", "--publish"])
    output = json.loads(capsys.readouterr().out)
    assert result == 0 and output["composition_pending"] is True
    assert output["day"]["dog_ids"] == ["dog"] and output["publication"] is None
    store = Store(database)
    try:
        assert store.status()["requests"] == {"needs_review": 1}
        assert store.db.execute("SELECT count(*) FROM membership").fetchone()[0] == 1
    finally:
        store.close()
    assert len(calls) == 1
