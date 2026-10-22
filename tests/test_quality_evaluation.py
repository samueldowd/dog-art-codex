"""Synthetic mechanics tests; these do not establish real dog/calibration quality."""

import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime

import httpx
import pytest
from PIL import Image

from dog_art.contracts import CropRef, DogDescription, DogObservation, ImageFeature
from dog_art.description import DescriptionError
from dog_art.description.quality import (
    LocalVisibilityAssessor,
    VisibilityCase,
    VisibilityPolicy,
    parse_visibility,
    qualify_observation,
)
from dog_art.identity.evaluation import (
    LabeledSample,
    dataset_fingerprint,
    evaluate,
    select_calibration,
)
from dog_art.identity.matching import Calibration

MODEL = "qwen3-vl:4b"
DIGEST = "a" * 64
CAMERAS = ("east", "driveway")


def raw_visibility(**kwargs):
    return {
        "full_body": True,
        "dog_count": 1,
        "handler_present": False,
        "framing": "complete",
        "body_visibility": "clear",
        "blur": "low",
        "lighting": "adequate",
        "visible_regions": ["head", "torso", "forelegs", "hindlegs", "paws", "tail"],
        "occluded_regions": [],
        "uncertainty": [],
        **kwargs,
    }


def assessment(crop_hash="b" * 64, **kwargs):
    return parse_visibility(
        raw_visibility(**kwargs), model=MODEL, digest=DIGEST, crop_sha256=crop_hash
    )


def observation(tmp_path):
    path = tmp_path / "dog.png"
    Image.new("RGB", (64, 64), "gray").save(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    now = datetime(2026, 10, 22, 12, tzinfo=UTC)
    crop = CropRef(path, digest, now, (0, 0, 64, 64), (64, 64), 0.9, False)
    return DogObservation("obs", "event", "track", "east", now, (crop,), 0.9)


def policy():
    cases = []
    for camera in CAMERAS:
        cases += [
            VisibilityCase("good-" + camera, camera, True, assessment()),
            VisibilityCase(
                "bad-" + camera, camera, False, assessment(full_body=False, framing="clipped")
            ),
        ]
    return VisibilityPolicy(
        "synthetic-evaluation-fixture",
        MODEL,
        DIGEST,
        "offline-test-reviewer",
        "c" * 64,
        ("reference-event",),
        CAMERAS,
        tuple(cases),
    )


def test_visibility_transport_exact_model_think_false_and_crop_binding(tmp_path):
    obs = observation(tmp_path)
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": MODEL, "digest": DIGEST}]})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["vision", "thinking"]})
        payload = json.loads(request.content)
        assert payload["think"] is False and payload["format"]["additionalProperties"] is False
        assert payload["model"] == MODEL and len(payload["messages"][0]["images"]) == 1
        return httpx.Response(
            200,
            json={
                "model": MODEL,
                "done": True,
                "message": {"content": json.dumps(raw_visibility())},
            },
        )

    assessor = LocalVisibilityAssessor(
        {
            "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
            "OLLAMA_MODEL": MODEL,
            "OLLAMA_MODEL_DIGEST": DIGEST,
        },
        httpx.Client(transport=httpx.MockTransport(respond)),
    )
    evidence = assessor.assess_views(obs)
    assert evidence[0].crop_sha256 == obs.crops[0].sha256
    assert all(r.url.host == "127.0.0.1" for r in requests)
    assert obs.crops[0].full_body is False


def test_full_body_requires_separate_reviewed_policy_and_preserves_original(tmp_path):
    obs = observation(tmp_path)
    initial = asdict(obs)
    ev = (assessment(obs.crops[0].sha256),)
    pending, receipt = qualify_observation(obs, ev)
    assert not pending.crops[0].full_body and receipt["policy"] is None
    qualified, receipt = qualify_observation(obs, ev, policy())
    assert qualified.crops[0].full_body and qualified.visibility == "full_body"
    assert asdict(obs) == initial and obs.crops[0].full_body is False
    assert receipt["policy"]["case_count"] == 4
    with pytest.raises(ValueError, match="different crop"):
        qualify_observation(obs, (assessment("0" * 64),), policy())


@pytest.mark.parametrize(
    "changes",
    [
        {"full_body": None},
        {"framing": "clipped"},
        {"body_visibility": "partial"},
        {"dog_count": 2},
        {"handler_present": True},
        {"blur": "unknown"},
        {"lighting": "unknown"},
        {"uncertainty": ["cannot see paws"]},
        {"visible_regions": ["head", "torso"]},
    ],
)
def test_visibility_uncertain_partial_multidog_handler_never_qualified(tmp_path, changes):
    obs = observation(tmp_path)
    out, _ = qualify_observation(obs, (assessment(obs.crops[0].sha256, **changes),), policy())
    assert not out.crops[0].full_body


def test_visibility_malformed_conflict_and_bad_calibration_fail_closed(tmp_path):
    with pytest.raises(DescriptionError):
        assessment(full_body="true")
    with pytest.raises(DescriptionError):
        assessment(occluded_regions=["head"])
    obs = observation(tmp_path)
    invalid = replace(policy(), reference_event_ids=("good-east",))
    out, receipt = qualify_observation(obs, (assessment(obs.crops[0].sha256),), invalid)
    assert not out.crops[0].full_body and "invalid" in receipt["reasons"][0]
    false_acceptance = replace(
        policy(),
        cases=(VisibilityCase("false-east", "east", False, assessment()),) + policy().cases,
    )
    with pytest.raises(ValueError, match="false acceptance"):
        false_acceptance.approved_conditions()
    missing_camera = replace(policy(), cases=policy().cases[:2])
    with pytest.raises(ValueError, match="camera"):
        missing_camera.approved_conditions()


def vector(values):
    return ImageFeature(tuple(values), "synthetic-image-fixture", DIGEST, "rgb:test")


def samples():
    result = []
    for split, day, values in [
        ("reference", "2026-10-20", {"a": (1, 0, 0), "b": (0, 1, 0)}),
        ("calibration", "2026-10-21", {"a": (0.95, 0.05, 0), "b": (0.05, 0.95, 0), "c": (0, 0, 1)}),
        ("evaluation", "2026-10-22", {"a": (0.99, 0.01, 0), "b": (0.01, 0.99, 0), "c": (0, 0, 1)}),
    ]:
        for dog, vals in values.items():
            camera = (
                ("east" if dog == "a" else "driveway")
                if split == "reference"
                else ("driveway" if dog == "a" else "east")
            )
            oid = split + "-" + dog
            result.append(
                LabeledSample(
                    oid,
                    "event-" + oid,
                    "visit-" + oid,
                    camera,
                    day,
                    dog,
                    (vector(vals),),
                    DogDescription(coat_colors=("white",)),
                    0.9,
                    split,
                    "same-coat-lookalikes" if dog in {"a", "b"} else None,
                    provenance="synthetic_test",
                    recognizable=True,
                    expected_abstention=False,
                )
            )
        if split != "reference":
            for reason, dog, vals, quality in (
                ("low_quality", "b", (0, 1, 0), 0.1),
                ("ambiguous", "a", (1, 1, 0), 0.9),
            ):
                oid = split + "-" + reason
                result.append(
                    LabeledSample(
                        oid,
                        "event-" + oid,
                        "visit-" + oid,
                        "east" if dog == "b" else "driveway",
                        day,
                        dog,
                        (vector(vals),),
                        DogDescription(coat_colors=("white",)),
                        quality,
                        split,
                        "same-coat-lookalikes",
                        "synthetic_test",
                        recognizable=False,
                        expected_abstention=True,
                        abstention_reason=reason,
                    )
                )
    return tuple(result)


def test_measured_grid_and_independent_holdout_metrics():
    data = samples()
    result = select_calibration(
        data,
        required_cameras=CAMERAS,
        reviewed_by="offline-fixture-review",
        version="synthetic-v1",
        allow_synthetic=True,
    )
    assert not result.promotable and result.calibration.validation_level == "test_only"
    assert "synthetic evaluation is test-only" in result.blocked_reason
    assert result.calibration_metrics.reuse_rate == 1
    assert result.evaluation_metrics.correct_reuse == 2
    assert result.evaluation_metrics.false_merges == 0
    assert result.evaluation_metrics.false_splits == 0
    assert result.evaluation_metrics.correct_new == 1
    assert result.evaluation_metrics.cross_camera_returns == 2
    assert result.evaluation_metrics.cross_day_returns == 2
    assert result.calibration.dataset_sha256 == dataset_fingerprint(data)
    assert result.scored_grid_size > 0
    assert result.receipt()["acceptance"]["minimum_recognizable_return_reuse"] == 0.9
    assert result.evaluation_metrics.expected_returns == 2
    assert result.evaluation_metrics.expected_abstentions == 2
    assert result.evaluation_metrics.correct_abstentions == 2
    assert result.evaluation_metrics.abstention_errors == 0
    assert set(result.calibration.enrollment_event_ids).isdisjoint(
        result.calibration.evaluation_event_ids
    )


def test_holdout_false_merges_block_promotion_without_threshold_retuning():
    data = samples()
    swapped = tuple(
        replace(s, features=(vector((0, 1, 0) if s.dog_label == "a" else (1, 0, 0)),))
        if s.split == "evaluation" and s.dog_label in {"a", "b"} and s.recognizable
        else s
        for s in data
    )
    result = select_calibration(
        swapped,
        required_cameras=CAMERAS,
        reviewed_by="offline-fixture-review",
        version="synthetic-v1",
        allow_synthetic=True,
    )
    assert not result.promotable and "independent evaluation failed" in result.blocked_reason
    assert result.evaluation_metrics.false_merges == 2
    assert result.evaluation_metrics.correct_reuse == 0
    assert result.calibration is None


@pytest.mark.parametrize(
    "case",
    [
        "visit_leak",
        "event_leak",
        "no_hard_negatives",
        "no_return",
        "no_novel",
        "one_camera",
        "artwork",
    ],
)
def test_insufficient_evidence_blocks_instead_of_guessing(case):
    data = samples()
    if case == "visit_leak":
        data = tuple(
            replace(s, visit_id=data[0].visit_id) if s.observation_id == "evaluation-a" else s
            for s in data
        )
    elif case == "event_leak":
        data = tuple(
            replace(s, event_id=data[0].event_id) if s.observation_id == "evaluation-a" else s
            for s in data
        )
    elif case == "no_hard_negatives":
        data = tuple(replace(s, hard_negative_group=None) for s in data)
    elif case == "no_return":
        data = tuple(
            replace(s, dog_label="unseen-" + s.dog_label) if s.split == "evaluation" else s
            for s in data
        )
    elif case == "no_novel":
        data = tuple(s for s in data if s.dog_label != "c")
    elif case == "one_camera":
        data = tuple(replace(s, camera="east") for s in data)
    elif case == "artwork":
        data = (
            replace(data[0], features=(replace(data[0].features[0], provenance="generated_art"),)),
        ) + data[1:]
    result = select_calibration(
        data,
        required_cameras=CAMERAS,
        reviewed_by="offline-fixture-review",
        version="synthetic-v1",
        allow_synthetic=True,
    )
    assert not result.promotable and result.blocked_reason and result.calibration is None


def test_fixed_policy_reports_false_splits_and_abstention():
    data = samples()
    profile = Calibration(
        "synthetic",
        "synthetic-image-fixture",
        DIGEST,
        "rgb:test",
        3,
        0.99999,
        0.99998,
        0.1,
        0.9,
        dataset_fingerprint(data),
        "test-review",
        ("reference-event",),
        ("eval-event",),
        2,
        2,
        None,
        "synthetic_test",
        validation_level="provisional",
    )
    measured = evaluate(data, profile, required_cameras=CAMERAS, allow_synthetic=True)
    assert measured.false_splits == 3 and measured.correct_reuse == 0
    profile = replace(profile, new_threshold=0.1)
    measured = evaluate(data, profile, required_cameras=CAMERAS, allow_synthetic=True)
    assert measured.abstentions == 4 and measured.correct_abstentions == 2
    assert measured.unexpected_abstentions == 2 and not measured.passes


def test_visibility_policy_local_roundtrip_and_no_grid_silent_truncation(tmp_path):
    path = tmp_path / "visibility.json"
    path.write_text(json.dumps(asdict(policy())))
    loaded = VisibilityPolicy.load(path)
    assert loaded.receipt() == policy().receipt()
    result = select_calibration(
        samples(),
        required_cameras=CAMERAS,
        reviewed_by="test-review",
        version="synthetic",
        allow_synthetic=True,
        max_grid_size=0,
    )
    assert not result.promotable and "finite evaluation bound" in result.blocked_reason


def schema_fixture():
    """Artificial parser fixture only; never used to assert real identity quality."""
    return Calibration(
        version="unit-schema-only",
        model="unit-encoder",
        digest=DIGEST,
        preprocessing="unit-rgb",
        dimension=3,
        match_threshold=0.9,
        new_threshold=0.2,
        score_margin=0.1,
        minimum_quality=0.5,
        dataset_sha256="d" * 64,
        reviewed_by="unit-parser-fixture",
        enrollment_event_ids=("unit-reference",),
        evaluation_event_ids=("unit-eval",),
        same_dog_pairs=10,
        different_dog_pairs=10,
        false_merges=0,
        evidence_provenance="real_camera",
        validation_level="approved",
        samples=13,
        expected_returns=10,
        correct_reuse=9,
        false_splits=1,
        abstentions=2,
        new_dogs=1,
        correct_new=1,
        cross_camera_returns=10,
        cross_day_returns=10,
        hard_negative_samples=10,
        unrecognizable_known=2,
        unrecognizable_samples=2,
        expected_abstentions=2,
        correct_abstentions=2,
        abstention_errors=0,
        unexpected_abstentions=0,
        low_quality_cases=1,
        ambiguous_cases=1,
        known_decisions=9,
        new_decisions=2,
    )


def test_approved_schema_requires_exact_heldout_90_percent_and_zero_merges(tmp_path):
    artificial = schema_fixture()
    path = tmp_path / "unit-only-calibration.json"
    path.write_text(json.dumps(asdict(artificial)))
    assert Calibration.load(path).correct_reuse == 9
    with pytest.raises(ValueError, match="90 percent"):
        replace(artificial, correct_reuse=8, false_splits=2).validate()
    with pytest.raises(ValueError, match="zero false-merge"):
        replace(artificial, false_merges=1, correct_new=0).validate()
    for field in ("correct_reuse", "expected_returns", "false_splits", "abstentions"):
        with pytest.raises(ValueError, match="heldout counts"):
            replace(artificial, **{field: None}).validate()
    with pytest.raises(ValueError, match="inconsistent"):
        replace(artificial, samples=14).validate()
    with pytest.raises(ValueError, match="heldout counts"):
        replace(artificial, correct_reuse=True).validate()


def test_old_unapproved_and_provisional_reports_cannot_enable_runtime(tmp_path):
    artificial = schema_fixture()
    old = asdict(artificial)
    for key in (
        "validation_level",
        "samples",
        "expected_returns",
        "correct_reuse",
        "false_splits",
        "abstentions",
        "new_dogs",
        "correct_new",
        "cross_camera_returns",
        "cross_day_returns",
        "hard_negative_samples",
    ):
        old.pop(key)
    path = tmp_path / "legacy-unit-report.json"
    path.write_text(json.dumps(old))
    with pytest.raises(ValueError, match="approved independent heldout"):
        Calibration.load(path)
    provisional = replace(artificial, validation_level="provisional")
    with pytest.raises(ValueError, match="approved independent heldout"):
        provisional.validate()
    with pytest.raises(ValueError, match="must not claim heldout"):
        provisional.validate(evaluation_only=True)


def test_synthetic_evaluation_requires_opt_in_and_never_loads_as_runtime(tmp_path):
    blocked = select_calibration(
        samples(), required_cameras=CAMERAS, reviewed_by="offline-test", version="synthetic"
    )
    assert not blocked.promotable and blocked.calibration is None
    tested = select_calibration(
        samples(),
        required_cameras=CAMERAS,
        reviewed_by="offline-test",
        version="synthetic",
        allow_synthetic=True,
    )
    assert tested.calibration.validation_level == "test_only" and not tested.promotable
    for field in (
        "samples",
        "expected_returns",
        "correct_reuse",
        "false_merges",
        "false_splits",
        "abstentions",
        "new_dogs",
        "correct_new",
        "cross_camera_returns",
        "cross_day_returns",
        "hard_negative_samples",
    ):
        assert getattr(tested.calibration, field) == getattr(tested.evaluation_metrics, field)
    path = tmp_path / "synthetic-test-only.json"
    path.write_text(json.dumps(asdict(tested.calibration)))
    with pytest.raises(ValueError, match="approved independent heldout"):
        Calibration.load(path)


@pytest.mark.parametrize(
    "split,reason",
    [
        ("calibration", "low_quality"),
        ("calibration", "ambiguous"),
        ("evaluation", "low_quality"),
        ("evaluation", "ambiguous"),
    ],
)
def test_each_independent_split_requires_human_labeled_abstention_classes(split, reason):
    data = tuple(s for s in samples() if not (s.split == split and s.abstention_reason == reason))
    result = select_calibration(
        data,
        required_cameras=CAMERAS,
        reviewed_by="offline-test",
        version="synthetic",
        allow_synthetic=True,
    )
    assert result.calibration is None and not result.promotable
    assert "lacks human-labeled low-quality and ambiguous" in result.blocked_reason


@pytest.mark.parametrize(
    "changes",
    [
        {"recognizable": None},
        {"expected_abstention": None},
        {"recognizable": False, "expected_abstention": False},
        {"recognizable": True, "expected_abstention": True},
        {"recognizable": False, "expected_abstention": True, "abstention_reason": "model_guess"},
    ],
)
def test_missing_or_contradictory_human_labels_fail_closed(changes):
    data = (replace(samples()[0], **changes),) + samples()[1:]
    result = select_calibration(
        data,
        required_cameras=CAMERAS,
        reviewed_by="offline-test",
        version="synthetic",
        allow_synthetic=True,
    )
    assert result.calibration is None and not result.promotable


def test_correct_known_assignment_to_human_ambiguous_input_is_still_unsafe():
    # Simulate a quality scorer incorrectly rating a human-labeled poor view as
    # high quality. Identity may be right, but automatic acceptance must abstain.
    data = tuple(
        replace(s, quality=0.9)
        if s.split == "evaluation" and s.abstention_reason == "low_quality"
        else s
        for s in samples()
    )
    result = select_calibration(
        data,
        required_cameras=CAMERAS,
        reviewed_by="offline-test",
        version="synthetic",
        allow_synthetic=True,
    )
    measured = result.evaluation_metrics
    assert measured.expected_returns == 2 and measured.correct_reuse == 2
    assert measured.reuse_rate == 1 and measured.false_merges == 0
    assert measured.expected_abstentions == 2 and measured.abstention_errors == 1
    assert not measured.passes and not result.promotable and result.calibration is None
    assert "abstention gate" in result.blocked_reason


def test_runtime_report_requires_new_abstention_evidence_even_with_passing_reuse():
    artificial = schema_fixture()
    for field in (
        "expected_abstentions",
        "correct_abstentions",
        "abstention_errors",
        "low_quality_cases",
        "ambiguous_cases",
        "unrecognizable_samples",
    ):
        with pytest.raises(ValueError, match="heldout counts"):
            replace(artificial, **{field: None}).validate()
    with pytest.raises(ValueError, match="insufficient heldout"):
        replace(artificial, low_quality_cases=0, ambiguous_cases=2).validate()
    # Counts remain internally coherent, yet a single unsafe acceptance fails.
    unsafe = replace(
        artificial, correct_abstentions=1, abstention_errors=1, abstentions=1, known_decisions=10
    )
    with pytest.raises(ValueError, match="abstention gate"):
        unsafe.validate()
