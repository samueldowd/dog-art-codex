import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from dog_art.clock import FrozenClock
from dog_art.contracts import CropRef, DogDescription, DogObservation, ImageFeature
from dog_art.runtime import Pipeline
from dog_art.settings import Settings, load_settings
from dog_art.vision.detector import YoloXDetector

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 22, 16, tzinfo=UTC)


def config(tmp_path):
    cfg = load_settings(ROOT / "config/app.toml", tmp_path / ".env", environ={})
    return Settings(
        {
            **cfg.values,
            "APP_DATA_ROOT": str(tmp_path / "state"),
            "MIN_FREE_DISK_MB": 0,
            "LOCAL_DOG_DETECTOR": "",
            "LOCAL_IMAGE_ENCODER": "",
            "OPENAI_GENERATION_ENABLED": False,
            "PUBLISH_ENABLED": False,
        }
    )


class Unavailable:
    def events(self, **kwargs):
        raise TimeoutError("secret-password")

    def close(self):
        pass


class Description:
    def describe(self, observation):
        return DogDescription(coat_colors=("white",), uncertainty=("visibility limited",))


class Encoder:
    def encode_views(self, observation):
        return tuple(
            ImageFeature((1.0, 0.0), "fixture", "a" * 64, "rgb-v1") for c in observation.crops
        )


@pytest.mark.parametrize("cached", [False, True])
def test_source_outage_does_not_block_rollover_or_work(tmp_path, cached):
    settings = config(tmp_path)
    clock = FrozenClock(NOW)
    pipe = Pipeline(
        settings, clock=clock, source=Unavailable(), describer=Description(), encoder=Encoder()
    )
    try:
        event = {
            "id": "event",
            "camera": "driveway_ptz",
            "label": "dog",
            "start_time": NOW.timestamp(),
            "end_time": NOW.timestamp() + 1,
            "false_positive": False,
            "has_snapshot": True,
        }
        from dog_art.frigate import EventIngestor

        EventIngestor(pipe.store, settings, clock).record(event)
        image = tmp_path / "state/real-fixture.png"
        Image.new("RGB", (100, 100), "white").save(image)
        crop = CropRef(
            image,
            hashlib.sha256(image.read_bytes()).hexdigest(),
            NOW,
            (0, 0, 100, 100),
            (100, 100),
            1,
            False,
        )
        obs = DogObservation("obs", "event", "track", "driveway_ptz", NOW, (crop,), 1)
        pipe._persist_observations((obs,))
        if cached:
            # An upgrade/model change must retain the previous successful local
            # inference and its exact model provenance, without re-description.
            pipe.store.db.execute(
                "INSERT INTO descriptions VALUES(?,?,?,?)",
                (
                    "obs",
                    "previous-model:4b",
                    "c" * 64,
                    json.dumps(asdict(Description().describe(obs))),
                ),
            )
        # Do not let the separate extract fixture consume this test's work item.
        pipe.store.db.execute("UPDATE jobs SET state='done' WHERE kind='extract'")
        status = pipe.tick(max_jobs=5)
        assert status["review"] == 1 and status["identities"] == 0
        assert pipe.store.db.execute("SELECT count(*) FROM descriptions").fetchone()[0] == 1
        assert pipe.store.db.execute("SELECT count(*) FROM features").fetchone()[0] == 1
        assert (
            pipe.store.db.execute(
                "SELECT count(*) FROM audit WHERE code='identity_decision'"
            ).fetchone()[0]
            == 1
        )
        assert (
            pipe.store.db.execute("SELECT state FROM jobs WHERE kind='describe'").fetchone()[0]
            == "done"
        )
        assert pipe.daily.latest().dog_ids == ()
        clock.value = datetime(2026, 10, 23, 5, tzinfo=UTC)
        pipe.tick(max_jobs=0)
        assert pipe.daily.latest().day == "2026-10-23" and pipe.store.status()["review"] == 1
        assert pipe.store.status()["requests"] == {}
    finally:
        pipe.close()


def test_missing_encoder_defers_and_retry_is_explicit(tmp_path):
    settings = config(tmp_path)
    pipe = Pipeline(settings, clock=FrozenClock(NOW))
    try:
        pipe.store.enqueue("unsupported", "dependency", {}, NOW.timestamp(), max_attempts=3)
        pipe.work_once()
        assert pipe.store.status()["jobs"] == {"dependency_wait": 1}
        assert pipe.retry_waiting() == 1
        assert pipe.store.status()["jobs"] == {"queued": 1}
    finally:
        pipe.close()


def test_review_rebuild_uses_observation_day_and_preserves_archive(tmp_path):
    settings = config(tmp_path)
    pipe = Pipeline(settings, clock=FrozenClock(NOW))
    try:
        pipe.daily.reconcile()
        archive = pipe.daily.latest()
        original = archive.output_path.read_bytes()
        pipe.store.db.execute("INSERT INTO dogs VALUES('dog',0,'accepted',NULL)")
        pipe.store.db.execute(
            "INSERT INTO events VALUES('event','driveway_ptz',?,?,'{}')",
            (NOW.timestamp(), NOW.timestamp() + 1),
        )
        payload = {"crops": [{"observed_at": NOW.isoformat()}]}
        pipe.store.db.execute(
            "INSERT INTO observations VALUES('obs','event','track','driveway_ptz',?,?,?,'accepted')",
            (NOW.timestamp(), json.dumps(payload), "dog"),
        )
        current = pipe.daily.rebuild_current_membership()
        assert current.dog_ids == ("dog",)
        pipe.store.db.execute(
            "UPDATE observations SET state='review',dog_id=NULL WHERE observation_id='obs'"
        )
        current = pipe.daily.rebuild_current_membership()
        assert current.dog_ids == ()
        assert archive.output_path.read_bytes() == original
    finally:
        pipe.close()


def test_detector_hash_policy_and_decode_no_network(tmp_path):
    import numpy as np

    model = tmp_path / "model.onnx"
    model.write_bytes(b"synthetic-detector-fixture")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "path": str(model),
                "sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
                "source": "official-test-fixture",
                "license": "test",
                "input_size": 416,
                "score_threshold": 0.3,
                "nms_threshold": 0.45,
            }
        )
    )
    output = np.zeros((1, 3549, 85), np.float32)
    # First stride8 cell: center208,208; width80,height80. COCO dog16.
    output[0, 0, :4] = [26, 26, np.log(10), np.log(10)]
    output[0, 0, 4] = 1
    output[0, 0, 21] = 0.9

    class Session:
        def get_inputs(self):
            return [SimpleNamespace(name="images", shape=[1, 3, 416, 416])]

        def run(self, outputs, inputs):
            assert inputs["images"].shape == (1, 3, 416, 416)
            return [output]

    detector = YoloXDetector(manifest, session=Session())
    items = detector.detect(Image.new("RGB", (416, 416), "white"))
    assert len(items) == 1 and items[0]["class_id"] == 16
    assert items[0]["box"] == pytest.approx((168, 168, 248, 248))
    model.write_bytes(b"changed")
    with pytest.raises(Exception, match="detector_hash_mismatch"):
        YoloXDetector(manifest, session=Session())


def test_live_doctor_separates_access_from_camera_readiness(tmp_path, monkeypatch):
    import dog_art.description
    import dog_art.frigate
    from dog_art.diagnostics import doctor

    class Source:
        def __init__(self, settings):
            pass

        def read(self, path):
            return b"0.18.0"

        def json(self, path):
            return {
                "cameras": {
                    "backyard_east": {"objects": {"track": ["deer"]}, "record": {"enabled": True}},
                    "driveway_ptz": {"objects": {"track": ["dog"]}, "record": {"enabled": False}},
                }
            }

        def close(self):
            pass

    class Model:
        def __init__(self, settings):
            pass

        def verify_model(self):
            return {"model": "test", "digest": "test"}

        def close(self):
            pass

    monkeypatch.setattr(dog_art.frigate, "FrigateClient", Source)
    monkeypatch.setattr(dog_art.description, "OllamaDescriber", Model)
    report = doctor(config(tmp_path), live=True)
    assert report["checks"]["frigate"]["read_access"] == "PASS"
    assert report["checks"]["frigate"]["status"] == "BLOCKED"
