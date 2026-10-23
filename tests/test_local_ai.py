import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import httpx
import numpy as np
import pytest
from PIL import Image

from dog_art.clock import FrozenClock
from dog_art.contracts import CropRef, DogDescription, DogObservation, ImageFeature
from dog_art.description import (
    DescriptionError,
    OllamaDescriber,
    combine_descriptions,
    parse_description,
)
from dog_art.identity import Calibration, EncoderManifest, IdentityEngine, OnnxImageEncoder, decide
from dog_art.storage import Store

NOW = datetime(2026, 10, 22, 16, tzinfo=UTC)
DIGEST = "a" * 64


def observation(tmp_path, oid="obs", camera="east", day=0, colors=("white",), views=1):
    path = tmp_path / (oid + ".png")
    Image.new("RGB", (64, 64), "white").save(path)
    when = NOW + timedelta(days=day)
    crop = CropRef(
        path, hashlib.sha256(path.read_bytes()).hexdigest(), when, (0, 0, 64, 64), (64, 64), 1, True
    )
    return DogObservation(oid, "event-" + oid, "track", camera, when, (crop,) * views, 1)


def feature(values=(1.0, 0.0)):
    return ImageFeature(values, "test-encoder", DIGEST, "rgb-v1")


def description(**kwargs):
    return DogDescription(coat_colors=("white",), **kwargs)


class SyntheticCalibration(Calibration):
    """Explicit in-memory test double. Its serialized report fails runtime load."""

    def validate(self, *, evaluation_only=False):
        return super().validate(evaluation_only=True)


def calibration():
    # Deliberately simulated evidence tests mechanics only, never live identity quality.
    return SyntheticCalibration(
        "simulated-fixture-v1",
        "test-encoder",
        DIGEST,
        "rgb-v1",
        2,
        0.9,
        0.2,
        0.1,
        0.5,
        "b" * 64,
        "offline-fixture",
        ("fixture-enroll-event",),
        ("fixture-independent-event",),
        1,
        1,
        0,
        "synthetic_test",
        validation_level="test_only",
        samples=4,
        expected_returns=1,
        correct_reuse=1,
        false_splits=0,
        abstentions=2,
        new_dogs=1,
        correct_new=1,
        cross_camera_returns=1,
        cross_day_returns=1,
        hard_negative_samples=1,
        unrecognizable_known=2,
        unrecognizable_samples=2,
        expected_abstentions=2,
        correct_abstentions=2,
        abstention_errors=0,
        unexpected_abstentions=0,
        low_quality_cases=1,
        ambiguous_cases=1,
        known_decisions=1,
        new_decisions=1,
    )


def settings(**kwargs):
    return {
        "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
        "OLLAMA_MODEL": "vision:test",
        "OLLAMA_MODEL_DIGEST": DIGEST,
        "IDENTITY_MODE": "calibrated_auto",
        **kwargs,
    }


def persist(store, obs):
    with store.transaction() as db:
        db.execute(
            "INSERT INTO events VALUES(?,?,?,?,?)",
            (
                obs.event_id,
                obs.camera,
                obs.observed_at.timestamp(),
                obs.observed_at.timestamp(),
                "{}",
            ),
        )
        db.execute(
            "INSERT INTO observations(observation_id,event_id,track_id,camera,observed_at,payload) VALUES(?,?,?,?,?,?)",
            (
                obs.observation_id,
                obs.event_id,
                obs.track_id,
                obs.camera,
                obs.observed_at.timestamp(),
                json.dumps(
                    {"crops": [{"sha256": obs.crops[0].sha256, "provenance": "real_camera"}]}
                ),
            ),
        )


def test_description_strict_unknowns_and_conflicting_views():
    unknown = parse_description(json.loads(json.dumps(asdict(DogDescription()))))
    assert unknown.breed is None and unknown.markings is None
    with pytest.raises(DescriptionError):
        parse_description({"coat_colors": ["white"]})
    with pytest.raises(DescriptionError):
        parse_description({**json.loads(json.dumps(asdict(unknown))), "fur": 1})
    result = combine_descriptions(
        [description(markings="black left ear"), description(markings="white ears")]
    )
    assert result.markings is None and "conflicting views: markings" in result.uncertainty
    guessed = parse_description({**json.loads(json.dumps(asdict(unknown))), "breed": "poodle"})
    assert guessed.breed is None and guessed.uncertainty


def test_ollama_exact_digest_vision_json_retry_and_local_payload(tmp_path):
    calls, tries = [], [0]

    def serve(request):
        calls.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "vision:test", "digest": DIGEST}]})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["vision", "completion"]})
        body = json.loads(request.content)
        assert body["model"] == "vision:test" and body["format"]["additionalProperties"] is False
        assert body["messages"][0]["images"] and len(body["messages"][0]["images"]) == 1
        tries[0] += 1
        return httpx.Response(
            200,
            json={
                "model": "vision:test",
                "done": True,
                "message": {
                    "content": "not json" if tries[0] == 1 else json.dumps(asdict(description()))
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(serve))
    out = OllamaDescriber(settings(), client).describe(observation(tmp_path))
    assert out.coat_colors == ("white",) and tries[0] == 2
    assert all(r.url.host == "127.0.0.1" for r in calls)
    assert not any("/pull" in r.url.path for r in calls)


@pytest.mark.parametrize(
    "tag,digest,capabilities",
    [
        ("other", DIGEST, ["vision"]),
        ("vision:test", "wrong", ["vision"]),
        ("vision:test", DIGEST, ["completion"]),
    ],
)
def test_ollama_rejects_unverified_model(tag, digest, capabilities):
    def serve(request):
        return httpx.Response(
            200,
            json={"models": [{"name": tag, "digest": digest}]}
            if request.url.path == "/api/tags"
            else {"capabilities": capabilities},
        )

    with pytest.raises(DescriptionError):
        OllamaDescriber(
            settings(), httpx.Client(transport=httpx.MockTransport(serve))
        ).verify_model()


def test_real_provenance_and_crop_hash_required(tmp_path):
    obs = observation(tmp_path)
    bad = replace(obs, crops=(replace(obs.crops[0], provenance="generated_art"),))
    with pytest.raises(DescriptionError):
        OllamaDescriber(
            settings(),
            httpx.Client(
                transport=httpx.MockTransport(lambda r: pytest.fail("no request expected"))
            ),
        ).describe(bad)
    obs.crops[0].path.write_bytes(b"changed")
    with pytest.raises(DescriptionError):
        OllamaDescriber(
            settings(),
            httpx.Client(
                transport=httpx.MockTransport(lambda r: pytest.fail("no request expected"))
            ),
        ).describe(obs)


def test_calibrated_match_new_margin_unknown_and_mutable_accessories():
    refs = {"dog-a": [((feature(),), description(accessories="red collar"))]}
    assert (
        decide(
            (feature(),), description(accessories="blue harness"), refs, 1, calibration()
        ).outcome
        == "known"
    )
    assert decide((feature((0, 1)),), description(), refs, 1, calibration()).outcome == "new"
    assert decide((feature(),), description(), refs, 1).outcome == "uncertain"
    refs["dog-b"] = [((feature((0.999, 0.001)),), description())]
    assert decide((feature(),), description(), refs, 1, calibration()).outcome == "uncertain"
    assert decide((feature(),), description(), refs, 0.1, calibration()).outcome == "uncertain"
    assert (
        decide(
            (feature(),),
            description(uncertainty=("conflicting views: markings",)),
            refs,
            1,
            calibration(),
        ).outcome
        == "uncertain"
    )
    assert (
        decide(
            (replace(feature(), model_digest="changed"),), description(), refs, 1, calibration()
        ).outcome
        == "uncertain"
    )
    refs["dog-empty"] = []
    assert decide((feature((0, 1)),), description(), refs, 1, calibration()).outcome == "uncertain"


def test_conflicting_multi_view_and_calibration_independent_events():
    refs = {"dog-a": [((feature(),), description())]}
    assert (
        decide((feature(), feature((0, 1))), description(), refs, 1, calibration()).outcome
        == "uncertain"
    )
    with pytest.raises(ValueError):
        replace(calibration(), evaluation_event_ids=calibration().enrollment_event_ids).validate()
    with pytest.raises(ValueError):
        replace(calibration(), evidence_provenance="generated_art").validate()
    with pytest.raises(ValueError):
        decide(
            (replace(feature(), provenance="generated_art"),), description(), refs, 1, calibration()
        )


def test_uncalibrated_recorded_review_and_reviewed_assign(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    obs = observation(tmp_path)
    persist(store, obs)
    engine = IdentityEngine(store, settings(), FrozenClock(NOW))
    result = engine.process(obs, description(), (feature(),))
    assert result.outcome == "uncertain" and store.status()["identities"] == 0
    assert len(engine.review()) == 1
    assignment = engine.assign(obs.observation_id, reason="operator checked original crops")
    assert store.status()["identities"] == 1
    assert engine.process(obs, description(), (feature(),)).dog_id == assignment["dog_id"]
    engine.undo(assignment["correction_id"], reason="review reversal")
    assert store.db.execute("SELECT state FROM dogs").fetchone()[0] == "retired"
    assert store.db.execute("SELECT dog_id FROM observations").fetchone()[0] is None
    store.close()


def test_simultaneous_cross_camera_enrollment_serialized_and_restart(tmp_path):
    dbpath = tmp_path / "db.sqlite"
    first = observation(tmp_path, "first", "east")
    second = observation(tmp_path, "second", "driveway")
    store = Store(dbpath)
    persist(store, first)
    persist(store, second)
    store.close()

    def work(obs):
        store = Store(dbpath)
        try:
            return IdentityEngine(
                store, settings(), FrozenClock(NOW), calibration=calibration()
            ).process(obs, description(), (feature(),))
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(work, [first, second]))
    assert {r.outcome for r in results} == {"new", "known"}
    assert len({r.dog_id for r in results}) == 1
    later = observation(tmp_path, "later", "driveway", day=1)
    store = Store(dbpath)
    persist(store, later)
    result = IdentityEngine(store, settings(), FrozenClock(NOW), calibration=calibration()).process(
        later, description(), (feature(),)
    )
    assert result.outcome == "known" and result.dog_id == results[0].dog_id
    assert store.db.execute("SELECT count(*) FROM dogs").fetchone()[0] == 1
    assert store.db.execute("SELECT count(*) FROM requests").fetchone()[0] == 0
    store.close()


def test_reviewed_merge_split_undo_and_immutable_history(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    engine = IdentityEngine(store, settings(), FrozenClock(NOW))
    assigned = []
    for i in range(3):
        obs = observation(tmp_path, str(i))
        persist(store, obs)
        engine.process(obs, description(), (feature(),))
        assigned.append(engine.assign(obs.observation_id, reason="visual review")["dog_id"])
    original_payloads = [
        r[0] for r in store.db.execute("SELECT payload FROM observations ORDER BY observation_id")
    ]
    historical = tmp_path / "historical.png"
    historical.write_bytes(b"immutable collage bytes")
    before = hashlib.sha256(historical.read_bytes()).hexdigest()
    cid = engine.merge(assigned[0], assigned[1], reason="independent views reviewed")
    assert store.canonical(assigned[0]) == assigned[1]
    engine.undo(cid, reason="lookalike correction")
    assert store.canonical(assigned[0]) == assigned[0]
    cid = engine.merge(assigned[0], assigned[1], reason="merge for split test")
    split = engine.split(assigned[1], ["0"], reason="separate this observation")
    assert (
        store.db.execute("SELECT dog_id FROM observations WHERE observation_id='0'").fetchone()[0]
        == split["dog_id"]
    )
    engine.undo(split["correction_id"], reason="reverse split")
    assert (
        store.db.execute("SELECT dog_id FROM observations WHERE observation_id='0'").fetchone()[0]
        == assigned[0]
    )
    assert original_payloads == [
        r[0] for r in store.db.execute("SELECT payload FROM observations ORDER BY observation_id")
    ]
    assert hashlib.sha256(historical.read_bytes()).hexdigest() == before
    assert store.db.execute("SELECT count(*) FROM corrections").fetchone()[0] == 8
    store.close()


def test_undo_refuses_later_conflicting_assignment(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    obs = observation(tmp_path)
    persist(store, obs)
    engine = IdentityEngine(store, settings(), FrozenClock(NOW))
    engine.process(obs, description(), (feature(),))
    first = engine.assign(obs.observation_id, reason="first review")
    engine.assign(obs.observation_id, reason="later independent review")
    with pytest.raises(ValueError, match="later correction"):
        engine.undo(first["correction_id"], reason="unsafe stale undo")
    store.close()


def test_explicit_onnx_preprocessing_output_and_digest(tmp_path):
    path = tmp_path / "local.onnx"
    path.write_bytes(b"fake transport test model; never deployed")
    manifest = EncoderManifest(
        "test",
        path,
        hashlib.sha256(path.read_bytes()).hexdigest(),
        2,
        "rgb-unit-v1",
        32,
        32,
        "center_crop",
        (0, 0, 0),
        (1, 1, 1),
        "features",
        "none",
        "offline-fixture",
        "test-only",
    )

    class Port:
        name = "pixels"
        type = "tensor(float)"
        shape = [1, 3, 32, 32]

    class Output:
        name = "features"

    class Session:
        def get_inputs(self):
            return [Port()]

        def get_outputs(self):
            return [Output()]

        def run(self, outputs, feeds):
            assert outputs == ["features"] and feeds["pixels"].shape == (1, 3, 32, 32)
            assert np.allclose(feeds["pixels"], 1.0)
            return [np.array([[3, 4]], dtype=np.float32)]

    result = OnnxImageEncoder(manifest, session=Session()).encode_views(observation(tmp_path))
    assert np.allclose(result[0].values, (0.6, 0.8)) and result[0].model_digest == manifest.sha256
    with pytest.raises(ValueError, match="digest"):
        OnnxImageEncoder(replace(manifest, sha256="0" * 64), session=Session())

    class BadSession(Session):
        def run(self, outputs, feeds):
            return [np.array([[1, 2, 3]])]

    with pytest.raises(ValueError, match="dimension"):
        OnnxImageEncoder(manifest, session=BadSession()).encode(observation(tmp_path, "bad"))


def test_actual_cpu_onnx_runtime_executes_image_tensor(tmp_path):
    """Minimal local ReduceMean graph tests actual runtime, not learned identity quality.

    Encode the tiny public ONNX protobuf structure directly to avoid adding an
    export-time onnx dependency or downloading a model in the offline suite.
    """

    def varint(n):
        result = bytearray()
        while n > 127:
            result.append((n & 127) | 128)
            n >>= 7
        result.append(n)
        return bytes(result)

    def integer(field, value):
        return varint(field << 3) + varint(value)

    def blob(field, value):
        value = value.encode() if isinstance(value, str) else value
        return varint((field << 3) | 2) + varint(len(value)) + value

    def info(name, dimensions):
        shape = b"".join(blob(1, integer(1, d)) for d in dimensions)
        tensor_type = integer(1, 1) + blob(2, shape)
        return blob(1, name) + blob(2, blob(1, tensor_type))

    axes = blob(1, "axes") + integer(8, 2) + integer(8, 3) + integer(20, 7)
    keepdims = blob(1, "keepdims") + integer(3, 0) + integer(20, 2)
    node = (
        blob(1, "pixels")
        + blob(2, "features")
        + blob(4, "ReduceMean")
        + blob(5, axes)
        + blob(5, keepdims)
    )
    graph = (
        blob(1, node)
        + blob(2, "offline-test-graph")
        + blob(11, info("pixels", [1, 3, 32, 32]))
        + blob(12, info("features", [1, 3]))
    )
    model = (
        integer(1, 8)
        + blob(2, "dog-art-offline-fixture")
        + blob(7, graph)
        + blob(8, integer(2, 13))
    )
    path = tmp_path / "tiny.onnx"
    path.write_bytes(model)
    manifest = EncoderManifest(
        "synthetic-runtime-fixture",
        path,
        hashlib.sha256(model).hexdigest(),
        3,
        "unit-rgb",
        32,
        32,
        "stretch",
        (0, 0, 0),
        (1, 1, 1),
        "features",
        "none",
        "locally-generated-test-graph",
        "CC0-test",
    )
    encoder = OnnxImageEncoder(manifest)
    out = encoder.encode(observation(tmp_path, "actual-runtime"))
    assert np.allclose(out.values, np.ones(3) / np.sqrt(3))
    assert ":sha256:" in out.preprocessing
    # Exact preprocessing changes must create a different feature space.
    changed = OnnxImageEncoder(replace(manifest, resize="center_crop"))
    assert encoder.preprocessing != changed.preprocessing


def test_shadow_mode_never_promotes_calibrated_suggestion(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    first = observation(tmp_path, "shadow")
    persist(store, first)
    engine = IdentityEngine(
        store, settings(IDENTITY_MODE="shadow"), FrozenClock(NOW), calibration=calibration()
    )
    result = engine.process(first, description(), (feature(),))
    assert (
        result.outcome == "uncertain"
        and result.abstention_reason == "identity mode requires operator review"
    )
    assert store.db.execute("SELECT count(*) FROM dogs").fetchone()[0] == 0
    assert store.db.execute("SELECT count(*) FROM features").fetchone()[0] == 1
    store.close()


def test_rejected_threshold_configuration_discards_loaded_calibration(tmp_path, monkeypatch):
    store = Store(tmp_path / "db.sqlite")
    obs = observation(tmp_path, "threshold-mismatch")
    persist(store, obs)
    monkeypatch.setattr(Calibration, "load", lambda path: calibration())
    configured = settings(
        IDENTITY_CALIBRATION_PATH="unit-path-not-read",
        IDENTITY_MATCH_THRESHOLD=0.75,
        IDENTITY_NEW_THRESHOLD=0.2,
        IDENTITY_SCORE_MARGIN=0.1,
    )
    engine = IdentityEngine(store, configured, FrozenClock(NOW))
    assert engine.calibration is None and engine.calibration_error
    result = engine.process(obs, description(), (feature(),))
    assert result.outcome == "uncertain"
    assert result.abstention_reason == "independent calibration unavailable"
    assert store.db.execute("SELECT count(*) FROM dogs").fetchone()[0] == 0
    store.close()


def test_latest_human_visibility_rejection_dominates_model_qualified_crops(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    obs = observation(tmp_path, "negative-visibility")
    assert all(c.full_body for c in obs.crops)
    persist(store, obs)
    original = store.db.execute("SELECT payload FROM observations").fetchone()[0]
    engine = IdentityEngine(store, settings(), FrozenClock(NOW), calibration=calibration())
    store.audit(
        "visibility_review",
        {
            "observation_id": obs.observation_id,
            "full_body": False,
            "reviewer": "offline-test",
            "evidence": "synthetic-negative",
        },
        NOW.timestamp(),
    )
    result = engine.process(obs, description(), (feature(),))
    assert result.outcome == "uncertain"
    assert result.abstention_reason == "full-body visibility rejected by operator"
    assert store.db.execute("SELECT count(*) FROM dogs").fetchone()[0] == 0
    assert store.db.execute("SELECT payload FROM observations").fetchone()[0] == original
    # A later explicit human correction is authoritative; audit history survives.
    store.audit(
        "visibility_review",
        {
            "observation_id": obs.observation_id,
            "full_body": True,
            "reviewer": "offline-test",
            "evidence": "synthetic-correction",
        },
        NOW.timestamp(),
    )
    corrected = engine.process(obs, description(), (feature(),))
    assert corrected.outcome == "new"
    assert (
        store.db.execute("SELECT count(*) FROM audit WHERE code='visibility_review'").fetchone()[0]
        == 2
    )
    store.close()


def test_transient_multiview_pose_and_accessories_do_not_veto_identity():
    combined = combine_descriptions(
        [
            description(pose="walking left", accessories="red collar"),
            description(pose="turning right", accessories="collar obscured"),
        ]
    )
    assert "conflicting views: pose" in combined.uncertainty
    assert "conflicting views: accessories" in combined.uncertainty
    galleries = {
        "dog-a": [((feature(),), description(pose="standing", accessories="blue harness"))]
    }
    result = decide((feature(), feature()), combined, galleries, 1, calibration())
    assert result.outcome == "known" and result.dog_id == "dog-a"
    stable_conflict = replace(
        combined, uncertainty=combined.uncertainty + ("conflicting views: markings",)
    )
    assert decide((feature(),), stable_conflict, galleries, 1, calibration()).outcome == "uncertain"


def test_legacy_description_json_spacing_is_semantic_but_provenance_is_exact(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    obs = observation(tmp_path, "legacy-spaced-description")
    persist(store, obs)
    old_model, old_digest = "old-exact-model", "f" * 64
    spaced = json.dumps(asdict(description()), indent=2)
    store.db.execute(
        "INSERT INTO descriptions VALUES(?,?,?,?)",
        (obs.observation_id, old_model, old_digest, spaced),
    )
    engine = IdentityEngine(store, settings(), FrozenClock(NOW))
    result = engine.process(
        obs, description(), (feature(),), description_model=old_model, description_digest=old_digest
    )
    assert result.outcome == "uncertain"
    assert store.db.execute("SELECT payload FROM descriptions").fetchone()[0] == spaced
    with pytest.raises(ValueError, match="immutable description evidence differs"):
        engine.process(
            obs,
            description(),
            (feature(),),
            description_model=old_model,
            description_digest="e" * 64,
        )
    with pytest.raises(ValueError, match="immutable description evidence differs"):
        engine.process(
            obs,
            description(markings="different stable facts"),
            (feature(),),
            description_model=old_model,
            description_digest=old_digest,
        )
    store.close()


def test_per_observation_accepts_distinct_appearances_without_matching_and_replay_dedups(
    tmp_path, monkeypatch
):
    store = Store(tmp_path / "db.sqlite")
    first = observation(tmp_path, "appearance-one", "east")
    second = observation(tmp_path, "appearance-two", "driveway")
    persist(store, first)
    persist(store, second)

    def forbidden(*args, **kwargs):
        pytest.fail("per-observation mode must not load calibration or compare galleries")

    monkeypatch.setattr(Calibration, "load", forbidden)
    engine = IdentityEngine(
        store,
        settings(IDENTITY_MODE="per_observation", IDENTITY_CALIBRATION_PATH="unused-old-profile"),
        FrozenClock(NOW),
    )
    monkeypatch.setattr(engine, "_galleries", forbidden)
    one = engine.process(first, description(), (feature(),))
    two = engine.process(second, description(), (feature(),))
    replay = engine.process(first, description(), (feature(),))
    assert one.outcome == two.outcome == "new"
    assert one.dog_id != two.dog_id and replay.dog_id == one.dog_id
    assert replay.outcome == "known"
    assert not one.calibration_version and not one.candidates
    assert "recognition deferred" in one.rationale[0]
    assert "replay is not returning-dog recognition" in replay.rationale[0]
    assert store.db.execute("SELECT count(*) FROM dogs").fetchone()[0] == 2
    assert store.db.execute("SELECT count(*) FROM features").fetchone()[0] == 2
    assert store.db.execute("SELECT count(*) FROM descriptions").fetchone()[0] == 2
    # The existing runtime portrait seam deduplicates on this appearance ID.
    for result in (one, two, replay):
        store.enqueue(
            "portrait",
            "portrait:" + result.dog_id,
            {"dog_id": result.dog_id},
            NOW.timestamp(),
            max_attempts=1,
        )
    assert store.db.execute("SELECT count(*) FROM jobs WHERE kind='portrait'").fetchone()[0] == 2
    assert store.db.execute("SELECT count(*) FROM requests").fetchone()[0] == 0
    store.close()


@pytest.mark.parametrize(
    "condition",
    ["unknown_visibility", "human_rejected", "invalid_quality", "conflicting_appearance"],
)
def test_per_observation_retains_visibility_and_quality_review_gates(tmp_path, condition):
    store = Store(tmp_path / "db.sqlite")
    obs = observation(tmp_path, "quality-" + condition)
    facts = description()
    if condition == "unknown_visibility":
        obs = replace(obs, crops=(replace(obs.crops[0], full_body=False),))
    elif condition == "invalid_quality":
        obs = replace(obs, quality=0.0)
    elif condition == "conflicting_appearance":
        facts = description(uncertainty=("conflicting views: markings",))
    persist(store, obs)
    if condition == "human_rejected":
        store.audit(
            "visibility_review",
            {
                "observation_id": obs.observation_id,
                "full_body": False,
                "reviewer": "offline-test",
                "evidence": "synthetic-rejection",
            },
            NOW.timestamp(),
        )
    engine = IdentityEngine(store, settings(IDENTITY_MODE="per_observation"), FrozenClock(NOW))
    result = engine.process(obs, facts, (feature(),))
    assert result.outcome == "uncertain" and result.dog_id is None
    assert store.db.execute("SELECT count(*) FROM dogs").fetchone()[0] == 0
    assert store.db.execute("SELECT count(*) FROM features").fetchone()[0] == 1
    store.close()


def test_per_observation_manual_positive_review_qualifies_original_unchanged(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    obs = observation(tmp_path, "manual-appearance")
    obs = replace(obs, crops=(replace(obs.crops[0], full_body=False),))
    persist(store, obs)
    original = store.db.execute("SELECT payload FROM observations").fetchone()[0]
    store.audit(
        "visibility_review",
        {
            "observation_id": obs.observation_id,
            "full_body": True,
            "reviewer": "offline-test",
            "evidence": "synthetic-positive",
        },
        NOW.timestamp(),
    )
    engine = IdentityEngine(store, settings(IDENTITY_MODE="per_observation"), FrozenClock(NOW))
    result = engine.process(obs, description(), (feature(),))
    assert result.outcome == "new" and result.dog_id
    assert not obs.crops[0].full_body
    assert store.db.execute("SELECT payload FROM observations").fetchone()[0] == original
    store.close()


def test_new_appearance_requires_stable_facts_even_after_complete_silhouette_review(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    obs = observation(tmp_path, "unresolved-small-dog")
    obs = replace(obs, crops=(replace(obs.crops[0], full_body=False),))
    persist(store, obs)
    store.audit(
        "visibility_review",
        {
            "observation_id": obs.observation_id,
            "full_body": True,
            "reviewer": "offline-test",
            "evidence": "synthetic-silhouette-only",
        },
        NOW.timestamp(),
    )
    facts = DogDescription(
        visible_areas=("body",), uncertainty=("blurred appearance; stable facts unknown",)
    )
    engine = IdentityEngine(store, settings(IDENTITY_MODE="per_observation"), FrozenClock(NOW))
    result = engine.process(obs, facts, (feature(),))
    assert result.outcome == "uncertain" and result.dog_id is None
    assert result.abstention_reason == "insufficient observed stable appearance evidence"
    assert store.db.execute("SELECT count(*) FROM dogs").fetchone()[0] == 0
    assert store.db.execute("SELECT count(*) FROM features").fetchone()[0] == 1
    assert store.db.execute("SELECT count(*) FROM descriptions").fetchone()[0] == 1
    assert store.db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
    store.close()


@pytest.mark.parametrize(
    "facts",
    [
        DogDescription(),
        DogDescription(
            pose="walking",
            accessories="red collar",
            visible_areas=("body",),
            approximate_size="small",
            breed="guessed breed",
        ),
        DogDescription(coat_colors=("unknown",), markings="not visible", fur="uncertain"),
        DogDescription(markings="not clearly visible"),
        DogDescription(markings="cannot be determined from this image"),
        DogDescription(markings="unknown due to blur"),
    ],
)
def test_transient_context_and_unknown_placeholders_are_not_stable_appearance(tmp_path, facts):
    store = Store(tmp_path / "db.sqlite")
    obs = observation(tmp_path, "unknown-appearance")
    persist(store, obs)
    engine = IdentityEngine(store, settings(IDENTITY_MODE="per_observation"), FrozenClock(NOW))
    result = engine.process(obs, facts, (feature(),))
    assert result.outcome == "uncertain"
    assert result.abstention_reason == "insufficient observed stable appearance evidence"
    store.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("coat_colors", ("white",)),
        ("markings", "black patch on left flank"),
        ("proportions", "short legs and long torso"),
        ("fur", "short straight coat"),
        ("muzzle", "long narrow muzzle"),
        ("ears", "upright triangular ears"),
        ("tail", "curled tail"),
    ],
)
def test_one_observed_stable_fact_satisfies_new_appearance_minimum(tmp_path, field, value):
    store = Store(tmp_path / "db.sqlite")
    obs = observation(tmp_path, "stable-" + field)
    persist(store, obs)
    engine = IdentityEngine(store, settings(IDENTITY_MODE="per_observation"), FrozenClock(NOW))
    result = engine.process(obs, DogDescription(**{field: value}), (feature(),))
    assert result.outcome == "new" and result.dog_id
    assert not result.calibration_version and not result.candidates
    store.close()


def test_existing_unknown_appearance_entry_replay_is_preserved_without_new_entry(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    obs = observation(tmp_path, "previously-reviewed-entry")
    persist(store, obs)
    # Represent an existing operator-accepted entry created before this guard.
    store.db.execute(
        "INSERT INTO dogs(dog_id,created_at) VALUES(?,?)", ("prior-appearance", NOW.timestamp())
    )
    store.db.execute(
        "UPDATE observations SET dog_id=?,state='accepted' WHERE observation_id=?",
        ("prior-appearance", obs.observation_id),
    )
    engine = IdentityEngine(store, settings(IDENTITY_MODE="per_observation"), FrozenClock(NOW))
    result = engine.process(obs, DogDescription(), (feature(),))
    assert result.outcome == "known" and result.dog_id == "prior-appearance"
    assert store.db.execute("SELECT count(*) FROM dogs").fetchone()[0] == 1
    assert store.db.execute("SELECT count(*) FROM requests").fetchone()[0] == 0
    store.close()


@pytest.mark.parametrize(
    "phrase", ["not clearly visible", "cannot be determined from this image", "unknown due to blur"]
)
def test_unknown_explanations_are_not_stable_appearance(phrase):
    from dog_art.description import has_observed_appearance

    assert not has_observed_appearance(DogDescription(markings=phrase))


def test_explicit_partial_policy_accepts_observed_facts_without_falsifying_source(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    obs = observation(tmp_path, "authorized-partial")
    obs = replace(obs, crops=(replace(obs.crops[0], full_body=False),), visibility="partial")
    persist(store, obs)
    original_payload = store.db.execute("SELECT payload FROM observations").fetchone()[0]
    facts = DogDescription(
        coat_colors=("white",),
        visible_areas=("torso",),
        occluded_areas=("paws", "tail"),
        uncertainty=("complete silhouette unavailable",),
    )
    engine = IdentityEngine(
        store,
        settings(IDENTITY_MODE="per_observation", SOURCE_REFERENCE_POLICY="best_effort_partial"),
        FrozenClock(NOW),
    )
    result = engine.process(obs, facts, (feature(),))
    assert result.outcome == "new" and result.dog_id
    assert not obs.crops[0].full_body and obs.visibility == "partial"
    assert store.db.execute("SELECT payload FROM observations").fetchone()[0] == original_payload
    saved_facts = json.loads(store.db.execute("SELECT payload FROM descriptions").fetchone()[0])
    assert saved_facts["tail"] is None and saved_facts["markings"] is None
    assert saved_facts["occluded_areas"] == ["paws", "tail"]
    evidence = json.loads(
        store.db.execute("SELECT payload FROM audit WHERE code='identity_decision'").fetchone()[0]
    )
    assert evidence["source_reference_policy"] == "best_effort_partial"
    assert evidence["partial_reference_used"] is True
    assert evidence["source_full_body_verified"] is False
    assert evidence["source_full_body_flags"] == [False]
    assert "unseen markings unknown" in evidence["source_limitation"]
    assert any("complete source silhouette unverified" in item for item in result.rationale)
    assert engine.process(obs, facts, (feature(),)).dog_id == result.dog_id
    assert store.db.execute("SELECT count(*) FROM dogs").fetchone()[0] == 1
    store.close()


@pytest.mark.parametrize(
    "condition",
    ["human_rejected", "invalid_quality", "conflicting_appearance", "unknown_appearance"],
)
def test_partial_policy_never_overrides_other_appearance_safeguards(tmp_path, condition):
    store = Store(tmp_path / "db.sqlite")
    obs = observation(tmp_path, "partial-" + condition)
    obs = replace(obs, crops=(replace(obs.crops[0], full_body=False),), visibility="partial")
    facts = description()
    if condition == "invalid_quality":
        obs = replace(obs, quality=0.0)
    elif condition == "conflicting_appearance":
        facts = description(uncertainty=("conflicting views: markings",))
    elif condition == "unknown_appearance":
        facts = DogDescription(visible_areas=("body",), uncertainty=("appearance unknown",))
    persist(store, obs)
    if condition == "human_rejected":
        store.audit(
            "visibility_review",
            {
                "observation_id": obs.observation_id,
                "full_body": False,
                "reviewer": "offline-test",
                "evidence": "synthetic-rejection",
            },
            NOW.timestamp(),
        )
    engine = IdentityEngine(
        store,
        settings(IDENTITY_MODE="per_observation", SOURCE_REFERENCE_POLICY="best_effort_partial"),
        FrozenClock(NOW),
    )
    result = engine.process(obs, facts, (feature(),))
    assert result.outcome == "uncertain" and result.dog_id is None
    evidence = json.loads(
        store.db.execute("SELECT payload FROM audit WHERE code='identity_decision'").fetchone()[0]
    )
    assert evidence["partial_reference_used"] is False
    assert store.db.execute("SELECT count(*) FROM dogs").fetchone()[0] == 0
    assert not obs.crops[0].full_body
    store.close()


@pytest.mark.parametrize("mode", ["shadow", "calibrated_auto"])
def test_partial_policy_cannot_bypass_full_body_in_recognition_modes(tmp_path, mode):
    store = Store(tmp_path / "db.sqlite")
    obs = observation(tmp_path, "other-mode-" + mode)
    obs = replace(obs, crops=(replace(obs.crops[0], full_body=False),))
    persist(store, obs)
    engine = IdentityEngine(
        store,
        settings(IDENTITY_MODE=mode, SOURCE_REFERENCE_POLICY="best_effort_partial"),
        FrozenClock(NOW),
        calibration=calibration(),
    )
    result = engine.process(obs, description(), (feature(),))
    assert result.outcome == "uncertain"
    assert result.abstention_reason == "full-body visibility not verified"
    assert store.db.execute("SELECT count(*) FROM dogs").fetchone()[0] == 0
    store.close()


@pytest.mark.parametrize("policy", [None, "full_body", "best_effort", "BEST_EFFORT_PARTIAL"])
def test_partial_reference_requires_exact_explicit_policy(tmp_path, policy):
    store = Store(tmp_path / "db.sqlite")
    obs = observation(tmp_path, "strict-source-policy")
    obs = replace(obs, crops=(replace(obs.crops[0], full_body=False),))
    persist(store, obs)
    selected = {} if policy is None else {"SOURCE_REFERENCE_POLICY": policy}
    engine = IdentityEngine(
        store, settings(IDENTITY_MODE="per_observation", **selected), FrozenClock(NOW)
    )
    assert engine.process(obs, description(), (feature(),)).outcome == "uncertain"
    store.close()
