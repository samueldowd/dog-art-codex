"""Native crops from timestamped independent dog tracks; ambiguous evidence abstains."""

import hashlib
import io
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image, ImageOps

from dog_art.contracts import CropRef, DogObservation
from dog_art.safety import owned_path

from .media import DecodedFrame, MediaError


@dataclass(frozen=True)
class TrackSample:
    """A box applies only at observed_at, with explicit xyxy source resolution.

    `full_body` and occlusion require detector/operator evidence; a Frigate dog box
    alone cannot prove either. Source is real_camera only. No reused fixed boxes.
    """

    track_id: str
    observed_at: datetime
    box: tuple[float, float, float, float]
    source_size: tuple[int, int]
    full_body: bool = False
    occluded: bool = False
    provenance: str = "real_camera"


class LocalTracker(Protocol):
    """Injected validated local detector/tracker, never downloaded implicitly.

    Implementations must associate each physical dog separately across decoded
    timestamps, including camera movement. Model/calibration acceptance is external.
    """

    def samples(self, frames: tuple[DecodedFrame, ...]) -> tuple[TrackSample, ...]: ...


def snapshot_sample(event, image: Image.Image):
    """Frigate 0.18 clean snapshot data.box is normalized (x,y,width,height).

    Only valid for /snapshot-clean.webp at data.snapshot_frame_time. Not for other
    video frames. Whole-body visibility remains unknown until independently checked.
    """
    data = event.metadata.get("data", {})
    if data.get("snapshot_clean") is not True:
        raise MediaError("clean_snapshot_unverified")
    try:
        x, y, width, height = data["box"]
        values = (x, y, width, height)
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError
        if not (
            x >= 0
            and y >= 0
            and width > 0
            and height > 0
            and x + width <= 1.000001
            and y + height <= 1.000001
        ):
            raise ValueError
        timestamp = data["snapshot_frame_time"]
        if type(timestamp) not in (float, int) or not math.isfinite(timestamp):
            raise ValueError
        observed_at = datetime.fromtimestamp(timestamp, UTC)
        if not event.start_time <= observed_at <= event.end_time:
            raise ValueError
        iw, ih = image.size
        return TrackSample(
            event.event_id,
            observed_at,
            (x * iw, y * ih, (x + width) * iw, (y + height) * ih),
            image.size,
        )
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        raise MediaError("snapshot_geometry_unverified") from None


def sharpness(image):
    """Laplacian variance as a ranking signal, not empirical identity quality."""
    pixels = np.asarray(image.convert("L"), dtype=np.float32)
    if min(pixels.shape) < 3:
        return 0.0
    laplacian = (
        4 * pixels[1:-1, 1:-1]
        - pixels[:-2, 1:-1]
        - pixels[2:, 1:-1]
        - pixels[1:-1, :-2]
        - pixels[1:-1, 2:]
    )
    return float(laplacian.var())


def _intersection(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


class CropExtractor:
    """Save bounded views per independent track; no geometry interpolation.

    Cropping precedes optional model resizing. Unknown/partial bodies remain
    review observations; blurred, overlapping, clipped or mismatched boxes reject.
    min_sharpness is an explicit policy requiring real-data calibration.
    """

    def __init__(self, settings, *, min_sharpness=None, max_time_delta=0.08, padding=0.08):
        self.settings = settings
        if (
            type(settings.get("FRAMES_PER_DOG", 6)) is not int
            or settings.get("FRAMES_PER_DOG", 6) < 1
        ):
            raise MediaError("crop_quality_unconfigured")
        self.min_sharpness = min_sharpness
        self.max_time_delta = max_time_delta
        self.padding = padding

    def extract(self, event, frames, samples, output_root: Path):
        if event.end_time is None:
            raise MediaError("event_in_progress")
        candidates, rejected = {}, []
        for sample in samples:
            if sample.provenance != "real_camera" or sample.observed_at.tzinfo is None:
                raise MediaError("non_camera_provenance")
            if not event.start_time <= sample.observed_at <= event.end_time:
                rejected.append((sample.track_id, "sample_outside_event"))
                continue
            matched = [
                frame
                for frame in frames
                if abs((frame.observed_at - sample.observed_at).total_seconds())
                <= self.max_time_delta
            ]
            if not matched:
                rejected.append((sample.track_id, "frame_time_mismatch"))
                continue
            frame = min(
                matched, key=lambda f: abs((f.observed_at - sample.observed_at).total_seconds())
            )
            width, height = frame.image.size
            sw, sh = sample.source_size
            if min(sw, sh) <= 0 or abs((sw / sh) / (width / height) - 1) > 0.005:
                rejected.append((sample.track_id, "source_aspect_mismatch"))
                continue
            box = tuple(
                v * scale
                for v, scale in zip(sample.box, (width / sw, height / sh, width / sw, height / sh))
            )
            if any(not math.isfinite(v) for v in box) or not (
                0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height
            ):
                rejected.append((sample.track_id, "invalid_box"))
                continue
            if sample.occluded or box[0] <= 0 or box[1] <= 0 or box[2] >= width or box[3] >= height:
                rejected.append((sample.track_id, "occluded_or_clipped"))
                continue
            others = [
                other
                for other in samples
                if other.track_id != sample.track_id
                and other.source_size == sample.source_size
                and abs((other.observed_at - sample.observed_at).total_seconds())
                <= self.max_time_delta
            ]
            if any(_intersection(sample.box, other.box) > 0 for other in others):
                rejected.append((sample.track_id, "ambiguous_overlapping_dogs"))
                continue
            padx, pady = (box[2] - box[0]) * self.padding, (box[3] - box[1]) * self.padding
            crop_box = (
                max(0, math.floor(box[0] - padx)),
                max(0, math.floor(box[1] - pady)),
                min(width, math.ceil(box[2] + padx)),
                min(height, math.ceil(box[3] + pady)),
            )
            if any(
                _intersection(
                    crop_box,
                    tuple(
                        value * scale
                        for value, scale in zip(
                            other.box, (width / sw, height / sh, width / sw, height / sh)
                        )
                    ),
                )
                > 0
                for other in others
            ):
                rejected.append((sample.track_id, "padded_crop_contains_other_dog"))
                continue
            image = frame.image.crop(crop_box).convert("RGB")
            score = sharpness(image)
            if self.min_sharpness is not None and score < self.min_sharpness:
                rejected.append((sample.track_id, "blurred"))
                continue
            quality = min(1.0, score / (score + 100)) * (1.0 if sample.full_body else 0.5)
            candidates.setdefault(sample.track_id, []).append(
                (quality, frame, crop_box, image, sample.full_body)
            )
        observations = []
        for track, views in sorted(candidates.items()):
            crops = []
            # Hash includes event+track; no untrusted IDs become path components.
            key = hashlib.sha256((event.event_id + ":" + track).encode()).hexdigest()
            unique = set()
            for quality, frame, box, image, full_body in sorted(
                views, key=lambda view: (-view[0], view[1].observed_at)
            ):
                marker = frame.observed_at.isoformat()
                if marker in unique:
                    continue
                unique.add(marker)
                if len(crops) >= self.settings.get("FRAMES_PER_DOG", 6):
                    break
                data = io.BytesIO()
                image.save(data, format="PNG")
                digest = hashlib.sha256(data.getvalue()).hexdigest()
                path = owned_path(output_root, key + "/" + digest + ".png", create_parent=True)
                if path.exists():
                    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                        raise MediaError("crop_integrity_failure")
                else:
                    with path.open("xb") as handle:
                        handle.write(data.getvalue())
                    path.chmod(0o600)
                crops.append(
                    CropRef(
                        path, digest, frame.observed_at, box, frame.image.size, quality, full_body
                    )
                )
            if crops:
                observation_id = uuid.uuid5(
                    uuid.NAMESPACE_URL, "dog-art:" + event.event_id + ":" + track
                ).hex
                observations.append(
                    DogObservation(
                        observation_id,
                        event.event_id,
                        track,
                        event.camera,
                        min(c.observed_at for c in crops),
                        tuple(crops),
                        max(c.quality for c in crops),
                        "full_body" if all(c.full_body for c in crops) else "unknown",
                    )
                )
        return tuple(observations), tuple(rejected)

    def model_input(self, crop):
        """Resize an already selected native crop only for local model transport."""
        image = decode_crop(crop)
        edge = self.settings.get("MODEL_INPUT_MAX_EDGE_PX", 1280)
        return ImageOps.contain(image, (edge, edge)) if max(image.size) > edge else image


def decode_crop(crop):
    from .media import decode_image

    data = crop.path.read_bytes()
    if hashlib.sha256(data).hexdigest() != crop.sha256:
        raise MediaError("crop_integrity_failure")
    return decode_image(data)
