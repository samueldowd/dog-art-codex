"""Shared immutable records; UTC timestamps and real-image provenance are explicit."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal


def utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timezone-aware timestamp required")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class EventRef:
    event_id: str
    camera: str
    label: str
    start_time: datetime
    end_time: datetime | None
    has_clip: bool = False
    has_snapshot: bool = False
    false_positive: bool = False
    metadata: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        utc(self.start_time)
        if self.end_time is not None:
            utc(self.end_time)
            if self.end_time < self.start_time:
                raise ValueError("event ends before start")


@dataclass(frozen=True)
class CropRef:
    path: Path
    sha256: str
    observed_at: datetime
    box: tuple[float, float, float, float]
    source_size: tuple[int, int]
    quality: float
    full_body: bool
    provenance: str = "real_camera"


@dataclass(frozen=True)
class DogObservation:
    observation_id: str
    event_id: str
    track_id: str
    camera: str
    observed_at: datetime
    crops: tuple[CropRef, ...]
    quality: float
    visibility: str = "unknown"


@dataclass(frozen=True)
class DogDescription:
    coat_colors: tuple[str, ...] = ()
    markings: str | None = None
    proportions: str | None = None
    approximate_size: str | None = None
    fur: str | None = None
    muzzle: str | None = None
    ears: str | None = None
    tail: str | None = None
    accessories: str | None = None
    pose: str | None = None
    visible_areas: tuple[str, ...] = ()
    occluded_areas: tuple[str, ...] = ()
    uncertainty: tuple[str, ...] = ()
    breed: str | None = None


@dataclass(frozen=True)
class ImageFeature:
    values: tuple[float, ...]
    model: str
    model_digest: str
    preprocessing: str
    provenance: str = "real_camera"


@dataclass(frozen=True)
class IdentityDecision:
    outcome: Literal["known", "new", "uncertain"]
    dog_id: str | None
    candidates: tuple[tuple[str, float], ...] = ()
    model_version: str = ""
    calibration_version: str = ""
    rationale: tuple[str, ...] = ()
    abstention_reason: str | None = None


@dataclass(frozen=True)
class PortraitRecipe:
    dog_id: str
    style_version: str
    recipe_hash: str
    prompt: str
    style_path: Path
    style_sha256: str
    model: str
    size: str
    quality: str
    input_policy: str = "artwork_only"


@dataclass(frozen=True)
class CollageRevision:
    day: str
    generation: str
    revision: int
    dog_ids: tuple[str, ...]
    portrait_hashes: tuple[str, ...]
    seed: int
    placements: tuple[dict, ...]
    width: int
    height: int
    background: str
    output_path: Path
    sha256: str
    created_at: datetime
    pending_dog_ids: tuple[str, ...] = ()
    portrait_policy: str = "all_accepted"


@dataclass(frozen=True)
class PublishReceipt:
    generation: str
    revision: int
    sha256: str
    server: str
    share: str
    relative_path: str
    uploaded_at: datetime
    replaced_at: datetime
    verified_at: datetime
    state: str = "verified"
