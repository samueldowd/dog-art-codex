"""Independent-event image-feature evaluation and measured threshold selection.

All inputs remain local. Labels/visit IDs are human evidence, not model guesses.
Selection uses only the calibration split. The evaluation split is never used to
choose thresholds; its zero false merges / >=90% reuse gate controls promotion.
"""

import hashlib
import itertools
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import date

import numpy as np

from dog_art.contracts import DogDescription, ImageFeature
from dog_art.identity.matching import Calibration, decide, normalized, space


class InsufficientEvaluation(ValueError):
    """Data or independent acceptance evidence cannot support promotion."""


@dataclass(frozen=True)
class LabeledSample:
    observation_id: str
    event_id: str
    visit_id: str
    camera: str
    observed_day: str
    dog_label: str
    features: tuple[ImageFeature, ...]
    description: DogDescription
    quality: float
    split: str
    hard_negative_group: str | None = None
    provenance: str = "real_camera"
    recognizable: bool | None = None
    expected_abstention: bool | None = None
    abstention_reason: str | None = None


@dataclass(frozen=True)
class EvaluationMetrics:
    samples: int
    expected_returns: int
    correct_reuse: int
    false_merges: int
    false_splits: int
    abstentions: int
    new_dogs: int
    correct_new: int
    cross_camera_returns: int
    cross_day_returns: int
    hard_negative_samples: int
    unrecognizable_known: int
    unrecognizable_samples: int
    expected_abstentions: int
    correct_abstentions: int
    abstention_errors: int
    unexpected_abstentions: int
    low_quality_cases: int
    ambiguous_cases: int
    known_decisions: int
    new_decisions: int

    @property
    def reuse_rate(self):
        return self.correct_reuse / self.expected_returns if self.expected_returns else 0.0

    @property
    def passes(self):
        return (
            self.expected_returns > 0
            and self.false_merges == 0
            and self.reuse_rate >= 0.9
            and self.expected_abstentions > 0
            and self.abstention_errors == 0
            and self.low_quality_cases > 0
            and self.ambiguous_cases > 0
        )

    def receipt(self):
        """Keep recognizable-return reuse separate from required abstentions."""
        return {
            **asdict(self),
            "recognizable_return_reuse_rate": self.reuse_rate,
            "observed_abstention_rate": self.abstentions / self.samples if self.samples else 0.0,
            "expected_abstention_success_rate": (
                self.correct_abstentions / self.expected_abstentions
                if self.expected_abstentions
                else 0.0
            ),
        }


@dataclass(frozen=True)
class EvaluationResult:
    calibration: Calibration | None
    calibration_metrics: EvaluationMetrics | None
    evaluation_metrics: EvaluationMetrics | None
    dataset_sha256: str
    scored_grid_size: int
    blocked_reason: str | None

    @property
    def promotable(self):
        return (
            self.calibration is not None
            and self.calibration.validation_level == "approved"
            and self.blocked_reason is None
        )

    def receipt(self):
        return {
            **asdict(self),
            "calibration_metrics": self.calibration_metrics.receipt()
            if self.calibration_metrics
            else None,
            "evaluation_metrics": self.evaluation_metrics.receipt()
            if self.evaluation_metrics
            else None,
            "promotable": self.promotable,
            "acceptance": {
                "minimum_recognizable_return_reuse": 0.9,
                "maximum_false_merges": 0,
                "maximum_abstention_errors": 0,
            },
        }


def dataset_fingerprint(samples):
    """Stable digest binds labels, split, event/visit identity and actual vectors."""
    values = [asdict(s) for s in sorted(samples, key=lambda s: s.observation_id)]
    return hashlib.sha256(json.dumps(values, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _prepare(samples, required_cameras, *, allow_synthetic=False):
    samples = tuple(samples)
    if not required_cameras or len(set(required_cameras)) != len(required_cameras):
        raise InsufficientEvaluation("explicit distinct target camera IDs required")
    if not samples or len({s.observation_id for s in samples}) != len(samples):
        raise InsufficientEvaluation("distinct labeled observations required")
    feature_space = None
    split_events = {key: set() for key in ("reference", "calibration", "evaluation")}
    split_visits = {key: set() for key in split_events}
    visits = {}
    for sample in samples:
        if (
            sample.provenance
            not in ({"real_camera", "synthetic_test"} if allow_synthetic else {"real_camera"})
            or not sample.features
            or not sample.event_id
            or not sample.visit_id
            or not sample.dog_label
            or sample.split not in split_events
            or sample.camera not in required_cameras
            or not math.isfinite(sample.quality)
            or not 0 <= sample.quality <= 1
            or type(sample.recognizable) is not bool
            or type(sample.expected_abstention) is not bool
            or sample.recognizable == sample.expected_abstention
            or (
                sample.expected_abstention
                and sample.abstention_reason not in {"low_quality", "ambiguous"}
            )
            or (not sample.expected_abstention and sample.abstention_reason is not None)
        ):
            raise InsufficientEvaluation("invalid real-camera independent label")
        try:
            date.fromisoformat(sample.observed_day)
        except ValueError:
            raise InsufficientEvaluation("explicit observation dates required") from None
        # A visit may include several dogs/tracks. One physical dog label cannot
        # be assigned inconsistent event/date provenance inside the same sample.
        visit_key = (sample.visit_id, sample.dog_label)
        visit_day = visits.setdefault(visit_key, sample.observed_day)
        if visit_day != sample.observed_day:
            raise InsufficientEvaluation("visit label spans inconsistent dates")
        for feature in sample.features:
            current = space(feature)
            if feature_space is not None and current != feature_space:
                raise InsufficientEvaluation("incompatible labeled feature spaces")
            feature_space = current
        split_events[sample.split].add(sample.event_id)
        split_visits[sample.split].add(sample.visit_id)
    for first, second in itertools.combinations(split_events, 2):
        if split_events[first] & split_events[second] or split_visits[first] & split_visits[second]:
            raise InsufficientEvaluation("event/physical-visit leakage between splits")
    if len({s.provenance for s in samples}) != 1:
        raise InsufficientEvaluation("real and synthetic evaluation evidence cannot be mixed")
    if any(not ids for ids in split_events.values()):
        raise InsufficientEvaluation(
            "reference, calibration and independent evaluation splits required"
        )
    refs = [s for s in samples if s.split == "reference"]
    galleries = {}
    for sample in refs:
        galleries.setdefault(sample.dog_label, []).append((sample.features, sample.description))
    groups = {}
    for sample in samples:
        if sample.hard_negative_group:
            groups.setdefault(sample.hard_negative_group, set()).add(sample.dog_label)
    hard_groups = {g for g, labels in groups.items() if len(labels) > 1}
    if not hard_groups:
        raise InsufficientEvaluation("explicit lookalike hard-negative labels required")
    for split in ("calibration", "evaluation"):
        cases = [s for s in samples if s.split == split]
        returns = [s for s in cases if s.dog_label in galleries and s.recognizable]
        if not returns:
            raise InsufficientEvaluation(f"{split} lacks independently labeled return visits")
        if not any(s.dog_label not in galleries and s.recognizable for s in cases):
            raise InsufficientEvaluation(f"{split} lacks independently labeled novel dogs")
        if {s.abstention_reason for s in cases if s.expected_abstention} != {
            "low_quality",
            "ambiguous",
        }:
            raise InsufficientEvaluation(
                f"{split} lacks human-labeled low-quality and ambiguous abstention examples"
            )
        if not any(s.hard_negative_group in hard_groups for s in cases):
            raise InsufficientEvaluation(f"{split} lacks lookalike hard-negative observations")
        if {s.camera for s in cases} != set(required_cameras):
            raise InsufficientEvaluation(f"{split} lacks evidence from every selected camera")
        if not any(
            any(r.camera != s.camera for r in refs if r.dog_label == s.dog_label) for s in returns
        ):
            raise InsufficientEvaluation(f"{split} lacks cross-camera return evidence")
        if not any(
            any(r.observed_day != s.observed_day for r in refs if r.dog_label == s.dog_label)
            for s in returns
        ):
            raise InsufficientEvaluation(f"{split} lacks cross-day return evidence")
    return samples, feature_space, refs, galleries, hard_groups


def _scores(sample, galleries):
    result = []
    for label, references in galleries.items():
        vectors = [normalized(f) for views, _ in references for f in views]
        score = min(max(float(np.dot(normalized(q), r)) for r in vectors) for q in sample.features)
        result.append((label, float(np.clip(score, -1.0, 1.0))))
    return tuple(sorted(result, key=lambda x: (-x[1], x[0])))


def evaluate(samples, calibration, *, split="evaluation", required_cameras, allow_synthetic=False):
    """Evaluate a fixed policy; never change thresholds based on this result."""
    if split not in {"calibration", "evaluation"}:
        raise InsufficientEvaluation("evaluation cannot reuse enrollment/reference samples")
    samples, _, refs, galleries, hard_groups = _prepare(
        samples, required_cameras, allow_synthetic=allow_synthetic
    )
    cases = [s for s in samples if s.split == split]
    counts = dict(
        samples=len(cases),
        expected_returns=0,
        correct_reuse=0,
        false_merges=0,
        false_splits=0,
        abstentions=0,
        new_dogs=0,
        correct_new=0,
        cross_camera_returns=0,
        cross_day_returns=0,
        hard_negative_samples=0,
        unrecognizable_known=0,
        unrecognizable_samples=0,
        expected_abstentions=0,
        correct_abstentions=0,
        abstention_errors=0,
        unexpected_abstentions=0,
        low_quality_cases=0,
        ambiguous_cases=0,
        known_decisions=0,
        new_decisions=0,
    )
    for sample in cases:
        known = sample.dog_label in galleries
        if known and sample.recognizable:
            counts["expected_returns"] += 1
            if any(r.camera != sample.camera for r in refs if r.dog_label == sample.dog_label):
                counts["cross_camera_returns"] += 1
            if any(
                r.observed_day != sample.observed_day
                for r in refs
                if r.dog_label == sample.dog_label
            ):
                counts["cross_day_returns"] += 1
        elif not known:
            counts["new_dogs"] += 1
        else:
            counts["unrecognizable_known"] += 1
        counts["unrecognizable_samples"] += not sample.recognizable
        counts["expected_abstentions"] += sample.expected_abstention
        counts["low_quality_cases"] += sample.abstention_reason == "low_quality"
        counts["ambiguous_cases"] += sample.abstention_reason == "ambiguous"
        counts["hard_negative_samples"] += sample.hard_negative_group in hard_groups
        decision = decide(
            sample.features,
            sample.description,
            galleries,
            sample.quality,
            calibration,
            _evaluation_only=True,
        )
        if decision.outcome == "uncertain":
            counts["abstentions"] += 1
            counts[
                "correct_abstentions" if sample.expected_abstention else "unexpected_abstentions"
            ] += 1
        elif decision.outcome == "known":
            counts["known_decisions"] += 1
            if decision.dog_id != sample.dog_label:
                counts["false_merges"] += 1
            elif sample.recognizable:
                counts["correct_reuse"] += 1
        else:
            counts["new_decisions"] += 1
            counts["false_splits" if known else "correct_new"] += 1
        if sample.expected_abstention and decision.outcome != "uncertain":
            counts["abstention_errors"] += 1
    return EvaluationMetrics(**counts)


def select_calibration(
    samples, *, required_cameras, reviewed_by, version, max_grid_size=10000, allow_synthetic=False
):
    """Search a finite grid of measured calibration scores, then holdout-evaluate.

    No guessed thresholds, dataset truncation, or evaluation-driven retry occurs.
    Insufficient/failed acceptance returns an explicit blocked result. The full
    receipt must be reviewed before writing any production calibration file.
    """
    samples = tuple(samples)
    try:
        prepared, feature_space, refs, galleries, _ = _prepare(
            samples, required_cameras, allow_synthetic=allow_synthetic
        )
        fingerprint = dataset_fingerprint(prepared)
        if not reviewed_by or not version:
            raise InsufficientEvaluation("explicit human label reviewer and version required")
        cases = [s for s in prepared if s.split == "calibration"]
        all_scores = [_scores(sample, galleries) for sample in cases]
        match_values = sorted({scores[0][1] for scores in all_scores})
        new_values = sorted({score for scores in all_scores for _, score in scores})
        margins = sorted(
            {
                scores[0][1] - scores[1][1]
                for scores in all_scores
                if len(scores) > 1 and scores[0][1] > scores[1][1]
            }
        )
        # A one-identity catalog cannot establish a measured alternative margin.
        qualities = sorted({s.quality for s in cases})
        grid = []
        for match, new, margin, quality in itertools.product(
            match_values, new_values, margins, qualities
        ):
            if -1 <= new < match <= 1 and 0 < margin <= 2:
                grid.append((match, new, margin, quality))
                if len(grid) > max_grid_size:
                    raise InsufficientEvaluation(
                        "measured grid exceeds finite evaluation bound; raise max_grid_size explicitly"
                    )
        if not grid:
            raise InsufficientEvaluation(
                "measured score grid cannot establish separated thresholds/margins"
            )
        reference_ids = tuple(sorted({s.event_id for s in prepared if s.split != "evaluation"}))
        evaluation_ids = tuple(sorted({s.event_id for s in prepared if s.split == "evaluation"}))
        expected_returns = sum(
            s.dog_label in galleries and s.recognizable for s in prepared if s.split == "evaluation"
        )
        negatives = sum(
            sum(label != s.dog_label for label in galleries)
            for s in prepared
            if s.split == "evaluation"
        )
        model, digest, preprocessing, dimension = feature_space
        best = None
        for match, new, margin, quality in grid:
            policy = Calibration(
                version,
                model,
                digest,
                preprocessing,
                dimension,
                match,
                new,
                margin,
                quality,
                fingerprint,
                reviewed_by,
                reference_ids,
                evaluation_ids,
                expected_returns,
                negatives,
                None,
                prepared[0].provenance,
                validation_level="provisional",
            )
            measured = evaluate(
                prepared,
                policy,
                split="calibration",
                required_cameras=required_cameras,
                allow_synthetic=allow_synthetic,
            )
            if not measured.passes:
                continue
            # Deterministic conservative tie-break among actual measurements:
            # prefer fewer false splits/abstentions, then stronger known threshold
            # and margin, then lower new threshold (more abstention on novelty).
            rank = (
                measured.false_splits,
                measured.abstentions,
                -measured.correct_new,
                -match,
                -margin,
                new,
                -quality,
            )
            if best is None or rank < best[0]:
                best = (rank, policy, measured)
        if best is None:
            return EvaluationResult(
                None,
                None,
                None,
                fingerprint,
                len(grid),
                "no measured calibration grid policy reaches recognizable reuse, false-merge and abstention gates",
            )
        _, policy, calibrated_metrics = best
        heldout = evaluate(
            prepared, policy, required_cameras=required_cameras, allow_synthetic=allow_synthetic
        )
        if not heldout.passes:
            return EvaluationResult(
                None,
                calibrated_metrics,
                heldout,
                fingerprint,
                len(grid),
                "independent evaluation failed recognizable reuse, false-merge or abstention gate",
            )
        approved = replace(
            policy,
            **asdict(heldout),
            validation_level="approved" if prepared[0].provenance == "real_camera" else "test_only",
        )
        approved.validate(evaluation_only=allow_synthetic)
        blocked_reason = (
            None
            if approved.validation_level == "approved"
            else "synthetic evaluation is test-only; production promotion forbidden"
        )
        return EvaluationResult(
            approved, calibrated_metrics, heldout, fingerprint, len(grid), blocked_reason
        )
    except (InsufficientEvaluation, ValueError, TypeError) as exc:
        # Messages contain only fixed reasons, never private feature/label payloads.
        reason = (
            str(exc)
            if isinstance(exc, InsufficientEvaluation)
            else "invalid or incompatible evaluation data"
        )
        return EvaluationResult(None, None, None, "", 0, reason)
