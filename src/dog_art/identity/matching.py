"""Calibrated, conservative image similarity with explicit feature-space compatibility."""

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from dog_art.contracts import IdentityDecision


def normalized(feature):
    if feature.provenance != "real_camera":
        raise ValueError("artwork cannot establish identity")
    v = np.asarray(feature.values, dtype=float)
    if v.ndim != 1 or not 1 <= len(v) <= 8192 or not np.isfinite(v).all():
        raise ValueError("invalid image feature")
    norm = float(np.linalg.norm(v))
    if norm <= 1e-12:
        raise ValueError("empty image feature")
    return v / norm


def space(feature):
    normalized(feature)
    if not all((feature.model, feature.model_digest, feature.preprocessing)):
        raise ValueError("feature provenance incomplete")
    return (feature.model, feature.model_digest, feature.preprocessing, len(feature.values))


@dataclass(frozen=True)
class Calibration:
    version: str
    model: str
    digest: str
    preprocessing: str
    dimension: int
    match_threshold: float
    new_threshold: float
    score_margin: float
    minimum_quality: float
    dataset_sha256: str
    reviewed_by: str
    enrollment_event_ids: tuple[str, ...]
    evaluation_event_ids: tuple[str, ...]
    same_dog_pairs: int
    different_dog_pairs: int
    false_merges: int | None
    evidence_provenance: str
    validation_level: str = "unapproved"
    samples: int | None = None
    expected_returns: int | None = None
    correct_reuse: int | None = None
    false_splits: int | None = None
    abstentions: int | None = None
    new_dogs: int | None = None
    correct_new: int | None = None
    cross_camera_returns: int | None = None
    cross_day_returns: int | None = None
    hard_negative_samples: int | None = None
    unrecognizable_known: int | None = None
    unrecognizable_samples: int | None = None
    expected_abstentions: int | None = None
    correct_abstentions: int | None = None
    abstention_errors: int | None = None
    unexpected_abstentions: int | None = None
    low_quality_cases: int | None = None
    ambiguous_cases: int | None = None
    known_decisions: int | None = None
    new_decisions: int | None = None

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.is_symlink() or path.stat().st_size > 256 * 1024:
            raise ValueError("unsafe calibration report")
        obj = json.loads(path.read_text())
        for field in ("enrollment_event_ids", "evaluation_event_ids"):
            obj[field] = tuple(obj[field])
        result = cls(**obj)
        result.validate()
        return result

    def validate(self, *, evaluation_only=False):
        numeric = (
            self.match_threshold,
            self.new_threshold,
            self.score_margin,
            self.minimum_quality,
        )
        if not all(
            isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
            for x in numeric
        ):
            raise ValueError("finite calibration thresholds required")
        if not (
            -1 <= self.new_threshold < self.match_threshold <= 1
            and 0 < self.score_margin <= 2
            and 0 <= self.minimum_quality <= 1
        ):
            raise ValueError("invalid calibrated threshold ordering")
        if (
            not self.version
            or not self.reviewed_by
            or not isinstance(self.dataset_sha256, str)
            or len(self.dataset_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.dataset_sha256)
            or self.evidence_provenance not in {"real_camera", "synthetic_test"}
            or not self.enrollment_event_ids
            or not self.evaluation_event_ids
            or any(
                not isinstance(ids, tuple)
                or len(set(ids)) != len(ids)
                or any(not isinstance(event_id, str) or not event_id for event_id in ids)
                for ids in (self.enrollment_event_ids, self.evaluation_event_ids)
            )
            or set(self.enrollment_event_ids) & set(self.evaluation_event_ids)
            or type(self.same_dog_pairs) is not int
            or self.same_dog_pairs < 1
            or type(self.different_dog_pairs) is not int
            or self.different_dog_pairs < 1
        ):
            raise ValueError("independent real-event calibration acceptance missing")
        if (
            not self.model
            or not self.digest
            or not self.preprocessing
            or type(self.dimension) is not int
            or not 1 <= self.dimension <= 8192
        ):
            raise ValueError("calibration feature space incomplete")
        if self.validation_level != "approved":
            if not evaluation_only or self.validation_level not in {"provisional", "test_only"}:
                raise ValueError("calibration lacks approved independent heldout metrics")
            # Provisional grid profiles carry no invented heldout counts. Only
            # the private evaluation path may score them; runtime fails closed.
            if self.validation_level == "provisional":
                if any(
                    getattr(self, name) is not None
                    for name in (
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
                        "unrecognizable_known",
                        "unrecognizable_samples",
                        "expected_abstentions",
                        "correct_abstentions",
                        "abstention_errors",
                        "unexpected_abstentions",
                        "low_quality_cases",
                        "ambiguous_cases",
                        "known_decisions",
                        "new_decisions",
                    )
                ):
                    raise ValueError("provisional policy must not claim heldout metrics")
                return
        if self.evidence_provenance != "real_camera" and not (
            evaluation_only and self.validation_level == "test_only"
        ):
            raise ValueError("synthetic calibration cannot enable runtime matching")
        metrics = {
            name: getattr(self, name)
            for name in (
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
                "unrecognizable_known",
                "unrecognizable_samples",
                "expected_abstentions",
                "correct_abstentions",
                "abstention_errors",
                "unexpected_abstentions",
                "low_quality_cases",
                "ambiguous_cases",
                "known_decisions",
                "new_decisions",
            )
        }
        if any(type(value) is not int or value < 0 for value in metrics.values()):
            raise ValueError("exact nonnegative heldout counts required")
        if (
            self.expected_returns < 1
            or self.new_dogs < 1
            or self.samples != self.expected_returns + self.new_dogs + self.unrecognizable_known
            or self.correct_reuse > self.expected_returns
            or self.false_splits > self.expected_returns - self.correct_reuse
            or self.correct_new > self.new_dogs
            or self.known_decisions + self.new_decisions + self.abstentions != self.samples
            or self.unrecognizable_samples != self.expected_abstentions
            or not self.unrecognizable_known <= self.unrecognizable_samples <= self.samples
            or self.correct_abstentions + self.abstention_errors != self.expected_abstentions
            or self.correct_abstentions + self.unexpected_abstentions != self.abstentions
            or self.low_quality_cases < 1
            or self.ambiguous_cases < 1
            or self.low_quality_cases + self.ambiguous_cases != self.expected_abstentions
            or not 1 <= self.cross_camera_returns <= self.expected_returns
            or not 1 <= self.cross_day_returns <= self.expected_returns
            or not 1 <= self.hard_negative_samples <= self.samples
            or self.same_dog_pairs < self.expected_returns
        ):
            raise ValueError("inconsistent or insufficient heldout evidence counts")
        if self.false_merges != 0 or self.correct_reuse / self.expected_returns < 0.9:
            raise ValueError("heldout 90 percent reuse and zero false-merge gate failed")
        if self.abstention_errors != 0:
            raise ValueError("heldout low-quality/ambiguous abstention gate failed")
        if (
            self.known_decisions != self.correct_reuse + self.false_merges
            or self.new_decisions != self.correct_new + self.false_splits
        ):
            raise ValueError("inconsistent accepted-decision outcome counts")

    def compatible(self, feature):
        return space(feature) == (self.model, self.digest, self.preprocessing, self.dimension)


def decide(features, description, galleries, quality, calibration=None, *, _evaluation_only=False):
    """galleries maps canonical IDs to [(feature_views, DogDescription), ...].

    Score is the worst query-view's best reference-view cosine, preventing an
    averaged good view from hiding a contradictory view. Thresholds are supplied
    only by reviewed independent-event calibration, never guessed defaults.
    """
    features = tuple(features)
    if not features:
        raise ValueError("image features required")
    feature_space = space(features[0])
    if any(space(f) != feature_space for f in features):
        raise ValueError("incompatible observation feature spaces")
    version = ":".join(map(str, feature_space))
    if calibration is None:
        return IdentityDecision(
            "uncertain",
            None,
            model_version=version,
            abstention_reason="independent calibration unavailable",
        )
    calibration.validate(evaluation_only=_evaluation_only)

    def uncertain(reason, candidates=()):
        return IdentityDecision(
            "uncertain", None, candidates, version, calibration.version, abstention_reason=reason
        )

    if not all(calibration.compatible(f) for f in features):
        return uncertain("encoder differs from calibrated feature space")
    if not math.isfinite(quality) or quality < calibration.minimum_quality:
        return uncertain("insufficient observation quality")
    if any(
        s.startswith("conflicting views:")
        and s.removeprefix("conflicting views:").strip() not in {"accessories", "pose"}
        for s in description.uncertainty
    ):
        return uncertain("conflicting appearance evidence")
    query = [normalized(f) for f in features]
    candidates = []
    incompatibility = False
    for dog_id, references in galleries.items():
        vectors = []
        for refs, reference_description in references:
            if any(space(f) != feature_space for f in refs):
                incompatibility = True
                continue
            # Accessories, pose, size and speculative breed never influence identity.
            # Stable color contradictions cause abstention, not a confident new dog.
            if (
                description.coat_colors
                and reference_description.coat_colors
                and set(description.coat_colors).isdisjoint(reference_description.coat_colors)
            ):
                if (
                    max(float(np.dot(q, normalized(f))) for q in query for f in refs)
                    >= calibration.match_threshold
                ):
                    return uncertain("visual and stable coat evidence conflict")
            vectors.extend(normalized(f) for f in refs)
        if vectors:
            score = min(max(float(np.dot(q, v)) for v in vectors) for q in query)
            candidates.append((dog_id, score))
        else:
            incompatibility = True
    ordered = tuple(sorted(candidates, key=lambda x: (-x[1], x[0])))
    if incompatibility:
        return uncertain("catalog contains incompatible or missing reference features", ordered)
    if not ordered:
        return IdentityDecision(
            "new", None, (), version, calibration.version, ("first calibrated enrollment",)
        )
    best = ordered[0]
    second = ordered[1][1] if len(ordered) > 1 else -1.0
    # View disagreement must not produce a false new enrollment.
    for q in query:
        if any(
            max(float(np.dot(q, normalized(f))) for refs, _ in references for f in refs)
            >= calibration.match_threshold
            for references in galleries.values()
        ):
            if best[1] < calibration.match_threshold:
                return uncertain("query views disagree on known identity", ordered)
    if best[1] >= calibration.match_threshold and best[1] - second >= calibration.score_margin:
        return IdentityDecision(
            "known",
            best[0],
            ordered,
            version,
            calibration.version,
            ("calibrated multi-view agreement and alternative margin",),
        )
    if best[1] <= calibration.new_threshold:
        return IdentityDecision(
            "new",
            None,
            ordered,
            version,
            calibration.version,
            ("calibrated separation from accepted catalog",),
        )
    return uncertain("ambiguous lookalike or insufficient candidate margin", ordered)
