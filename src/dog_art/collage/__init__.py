"""Deterministic local composition of validated portrait PNGs.

Rendering never mutates portrait bytes, mirrors an animal, publishes a file or
silently omits a member. Output PNG and adjacent JSON are create-only archives.
"""

import io
import json
import math
import os
import random
import tempfile
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageColor

from ..contracts import CollageRevision, utc
from ..safety import sha256


class LayoutCapacityError(ValueError):
    """Every member could not fit readably; preserve the last good output."""


class PortraitInputError(ValueError):
    """An input is missing, invalid or has no meaningful transparent silhouette."""


class ImmutableArchiveError(ValueError):
    """An archive name already exists or its recorded content differs."""


def revision_payload(revision: CollageRevision) -> dict:
    """Return JSON-compatible complete layout and content-hash provenance."""
    result = asdict(revision)
    result["output_path"] = str(revision.output_path)
    result["created_at"] = utc(revision.created_at).isoformat()
    result["renderer_version"] = "pillow-scattered-v1"
    result["silhouette_alpha_threshold"] = 16
    return result


def _write_new(path: Path, content: bytes):
    """Install complete bytes atomically and exclusively, never replace archives."""
    fd, name = tempfile.mkstemp(prefix=".collage-", suffix=".part", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def write_receipt(revision: CollageRevision):
    """Create a complete JSON sidecar, including safe crash-recovery receipts."""
    content = (json.dumps(revision_payload(revision), sort_keys=True, indent=2) + "\n").encode()
    _write_new(revision.output_path.with_suffix(".json"), content)


def load_revision(path: Path) -> CollageRevision:
    """Verify an immutable archive and read its adjacent layout receipt."""
    value = json.loads(path.with_suffix(".json").read_text())
    if value.get("renderer_version") != "pillow-scattered-v1":
        raise ImmutableArchiveError("unsupported renderer receipt")
    if Path(value["output_path"]) != path or sha256(path) != value["sha256"]:
        raise ImmutableArchiveError("archive content or location changed")
    return CollageRevision(
        **{
            k: value[k]
            for k in (
                "day",
                "generation",
                "revision",
                "seed",
                "width",
                "height",
                "background",
                "sha256",
            )
        },
        dog_ids=tuple(value["dog_ids"]),
        portrait_hashes=tuple(value["portrait_hashes"]),
        placements=tuple(value["placements"]),
        output_path=path,
        created_at=utc(datetime.fromisoformat(value["created_at"])),
    )


class CollageRenderer:
    """Render all input identities using a seeded, collision-free scattered grid.

    Source colors and aspect ratios remain unchanged apart from Pillow LANCZOS
    resampling and normal alpha compositing. Bounds use alpha >=16 because the
    supplied approved artwork has faint alpha fringes over its entire canvas.
    A two-pixel padding retains antialiasing around the meaningful silhouette.
    """

    def __init__(self, settings):
        self.width = settings.get("COLLAGE_WIDTH", 1920)
        self.height = settings.get("COLLAGE_HEIGHT", 1080)
        self.background = settings.get("COLLAGE_BACKGROUND", "#F3EBDD")
        self.margin = settings.get("COLLAGE_MARGIN_PX", 40)
        self.minimum = settings.get("COLLAGE_MIN_DOG_HEIGHT_PX", 120)
        if (self.width, self.height) != (1920, 1080):
            raise ValueError("collage must be exactly 1920x1080")
        if type(self.margin) is not int or not 0 <= self.margin < 540:
            raise ValueError("invalid collage margin")
        if type(self.minimum) is not int or self.minimum <= 0:
            raise ValueError("positive readable portrait height required")
        if settings.get("COLLAGE_LAYOUT", "scattered") != "scattered":
            raise ValueError("only scattered layout is supported")
        rgb = ImageColor.getrgb(self.background)
        if len(rgb) != 3:
            raise ValueError("opaque RGB background required")
        self.rgb = rgb

    def _portrait(self, path):
        try:
            with Image.open(path) as raw:
                if raw.format != "PNG" or raw.mode != "RGBA" or raw.width * raw.height > 25_000_000:
                    raise PortraitInputError("portrait must be a bounded RGBA PNG")
                raw.load()
                alpha = raw.getchannel("A")
                bbox = alpha.point(lambda p: 255 if p >= 16 else 0).getbbox()
                if bbox is None or alpha.getextrema()[0] == 255:
                    raise PortraitInputError("portrait requires a transparent full-body silhouette")
                bbox = (
                    max(0, bbox[0] - 2),
                    max(0, bbox[1] - 2),
                    min(raw.width, bbox[2] + 2),
                    min(raw.height, bbox[3] + 2),
                )
                return raw.crop(bbox), bbox, raw.size
        except (OSError, Image.DecompressionBombError) as exc:
            raise PortraitInputError("portrait cannot be decoded") from exc

    def render(
        self,
        portraits: Mapping[str, Path],
        *,
        day: str,
        generation: str,
        revision: int,
        seed: int,
        output_path: Path,
        created_at: datetime,
    ) -> CollageRevision:
        """Create a PNG + JSON archive. Existing outputs are never overwritten.

        Raises LayoutCapacityError before touching output when all dogs cannot
        meet the minimum height. The caller retains its previous valid revision.
        """
        utc(created_at)
        if type(seed) is not int or type(revision) is not int or revision < 0:
            raise ValueError("integer seed and nonnegative revision required")
        output_path = Path(output_path)
        if output_path.exists() or output_path.with_suffix(".json").exists():
            raise ImmutableArchiveError("archive already exists; choose a new revision")
        ids = tuple(sorted(portraits))
        images, boxes, sizes, hashes = {}, {}, {}, {}
        for dog_id in ids:
            path = Path(portraits[dog_id])
            hashes[dog_id] = sha256(path)
            images[dog_id], boxes[dog_id], sizes[dog_id] = self._portrait(path)
        canvas = Image.new("RGB", (self.width, self.height), self.rgb)
        placements = []
        if ids:
            # Each cell reserves complete portrait bounds plus an eight-pixel
            # gap. Seeded cell permutation, size and position scatter portraits.
            gap = 8
            inner_w, inner_h = self.width - 2 * self.margin, self.height - 2 * self.margin
            candidates = []
            for cols in range(1, len(ids) + 1):
                rows = math.ceil(len(ids) / cols)
                cell_w, cell_h = inner_w / cols, inner_h / rows
                scales = {
                    k: min(
                        (cell_w - gap) / images[k].width,
                        (cell_h - gap) / images[k].height,
                        800 / images[k].height,
                    )
                    for k in ids
                }
                heights = [math.floor(images[k].height * scales[k]) for k in ids]
                if min(heights) >= self.minimum:
                    score = sum(images[k].width * images[k].height * scales[k] ** 2 for k in ids)
                    candidates.append((score, cols, rows, scales))
            if not candidates:
                raise LayoutCapacityError(
                    f"{len(ids)} dogs cannot fit at >= {self.minimum}px height; prior output retained; increase display capacity or resolve layout policy"
                )
            _, cols, rows, scales = max(candidates, key=lambda x: (x[0], -x[1]))
            rng = random.Random(seed)
            cells = [(x, y) for y in range(rows) for x in range(cols)]
            rng.shuffle(cells)
            for dog_id, (col, row) in zip(ids, cells):
                image = images[dog_id]
                scale = scales[dog_id] * rng.uniform(
                    max(0.88, self.minimum / (image.height * scales[dog_id])), 1
                )
                width, height = (
                    max(1, round(image.width * scale)),
                    max(self.minimum, round(image.height * scale)),
                )
                left = self.margin + round(col * inner_w / cols) + gap // 2
                top = self.margin + round(row * inner_h / rows) + gap // 2
                right = self.margin + round((col + 1) * inner_w / cols) - gap // 2
                bottom = self.margin + round((row + 1) * inner_h / rows) - gap // 2
                # Floor avoids one-pixel round-up crossing cell reservations.
                fit = min((right - left) / width, (bottom - top) / height, 1)
                width, height = math.floor(width * fit), math.floor(height * fit)
                if height < self.minimum:
                    raise LayoutCapacityError(
                        "rounded layout violates readability; prior output retained"
                    )
                x, y = rng.randint(left, right - width), rng.randint(top, bottom - height)
                scaled = image.resize((width, height), Image.Resampling.LANCZOS)
                canvas.paste(scaled, (x, y), scaled.getchannel("A"))
                placements.append(
                    {
                        "dog_id": dog_id,
                        "portrait_sha256": hashes[dog_id],
                        "source_size": list(sizes[dog_id]),
                        "source_bbox": list(boxes[dog_id]),
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height,
                    }
                )
        output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        png = io.BytesIO()
        canvas.save(png, format="PNG", optimize=False, compress_level=6)
        import hashlib

        result = CollageRevision(
            day,
            generation,
            revision,
            ids,
            tuple(hashes[k] for k in ids),
            seed,
            tuple(placements),
            self.width,
            self.height,
            self.background,
            output_path,
            hashlib.sha256(png.getvalue()).hexdigest(),
            utc(created_at),
        )
        # Create-only writes preserve every prior archive and caller's output.
        _write_new(output_path, png.getvalue())
        write_receipt(result)
        return result


__all__ = [
    "CollageRenderer",
    "LayoutCapacityError",
    "PortraitInputError",
    "ImmutableArchiveError",
    "revision_payload",
    "load_revision",
]
