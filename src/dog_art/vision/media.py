"""Bounded local image/video decoders. No URL, protocol or shell input permitted."""

import io
import json
import math
import os
import re
import shutil
import subprocess
import warnings
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from PIL import Image, UnidentifiedImageError


class MediaError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def decode_image(data, *, max_bytes=33_554_432, max_pixels=33_177_600):
    """Check decoded dimensions before allocation and forbid animated media."""
    if not data or len(data) > max_bytes:
        raise MediaError("image_byte_limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.width * source.height > max_pixels or getattr(source, "n_frames", 1) != 1:
                    raise MediaError("image_pixel_limit")
                if source.format not in ("PNG", "JPEG", "WEBP"):
                    raise MediaError("unsupported_image")
                source.load()
                return source.convert("RGB")
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise MediaError("invalid_image") from None


@dataclass(frozen=True)
class DecodedFrame:
    image: Image.Image
    observed_at: object


class VideoDecoder:
    """Native-resolution one-frame decode using explicit verified clip UTC origin.

    FFmpeg timestamps (showinfo pts_time) are returned rather than inferred from a
    filename/requested seek. Each subprocess has time limits; frame dimensions,
    bytes, clip duration and output pixels are finite. A clip origin must be
    verified by integration; event.start_time alone does not prove clip origin.
    """

    def __init__(
        self,
        *,
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        max_bytes=104857600,
        max_seconds=60,
        max_pixels=33_177_600,
        timeout=30,
        runner=None,
    ):
        self.ffmpeg = shutil.which(ffmpeg) or ffmpeg
        self.ffprobe = shutil.which(ffprobe) or ffprobe
        self.max_bytes, self.max_seconds = max_bytes, max_seconds
        self.max_pixels, self.timeout = max_pixels, timeout
        self.runner = runner or subprocess.run

    def _run(self, args):
        try:
            result = self.runner(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
                check=False,
                env={"PATH": os.defpath, "LANG": "C"},
            )
        except FileNotFoundError:
            raise MediaError("decoder_missing") from None
        except subprocess.TimeoutExpired:
            raise MediaError("decoder_timeout") from None
        except OSError:
            raise MediaError("decoder_failed") from None
        if result.returncode:
            raise MediaError("decoder_failed")
        return result

    def frame(self, path: Path, *, clip_start_time, offset_seconds):
        path = Path(path)
        if clip_start_time.tzinfo is None:
            raise MediaError("clip_time_unverified")
        if not path.is_file() or path.is_symlink() or path.stat().st_size > self.max_bytes:
            raise MediaError("clip_byte_limit")
        if not math.isfinite(offset_seconds) or not 0 <= offset_seconds <= self.max_seconds:
            raise MediaError("clip_duration_limit")
        path = path.resolve()
        probe = self._run(
            [
                self.ffprobe,
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height:format=duration",
                "-of",
                "json",
                str(path),
            ]
        )
        if len(probe.stdout) > 16384:
            raise MediaError("invalid_clip_metadata")
        try:
            metadata = json.loads(probe.stdout)
            stream = metadata["streams"][0]
            width, height = int(stream["width"]), int(stream["height"])
            duration = float(metadata["format"]["duration"])
            if not (width > 0 and height > 0 and width * height <= self.max_pixels):
                raise MediaError("clip_pixel_limit")
            if (
                not math.isfinite(duration)
                or duration <= 0
                or duration > self.max_seconds
                or offset_seconds >= duration
            ):
                raise MediaError("clip_duration_limit")
        except (ValueError, KeyError, IndexError, TypeError):
            raise MediaError("invalid_clip_metadata") from None
        # select rather than blind seek: retain source presentation timestamp.
        result = self._run(
            [
                self.ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "info",
                "-threads",
                "1",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(path),
                "-an",
                "-sn",
                "-vf",
                f"select=gte(t\\,{offset_seconds:.9f}),showinfo",
                "-frames:v",
                "1",
                "-threads",
                "1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "pipe:1",
            ]
        )
        if len(result.stdout) != width * height * 3:
            raise MediaError("invalid_decoded_frame")
        timestamps = re.findall(rb"\bpts_time:([0-9.+-]+)", result.stderr)
        if not timestamps:
            raise MediaError("frame_time_missing")
        offset = float(timestamps[0])
        if not math.isfinite(offset) or offset < offset_seconds - 0.001 or offset > duration:
            raise MediaError("frame_time_invalid")
        return DecodedFrame(
            Image.frombytes("RGB", (width, height), result.stdout),
            clip_start_time + timedelta(seconds=offset),
        )
