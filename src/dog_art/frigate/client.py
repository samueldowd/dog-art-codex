"""Read-only Frigate 0.18 transport. All failures expose codes, never response bodies."""

import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

import httpx

from dog_art.contracts import EventRef
from dog_art.safety import safe_url

_ID = re.compile(r"[A-Za-z0-9_.-]{1,160}\Z")


class FrigateError(RuntimeError):
    def __init__(self, code, *, retryable=False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


def valid_id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value) or value in (".", ".."):
        raise FrigateError("invalid_event_id")
    return value


def parse_event(payload, cameras, *, completed=True):
    """Reject non-dogs, false positives, unselected cameras and incomplete events.

    Retains metadata privately for source geometry. Does not assert full-body quality.
    """
    if not isinstance(payload, dict):
        raise FrigateError("invalid_event")
    if payload.get("camera") not in cameras or payload.get("label") != "dog":
        return None
    # Frigate 0.18 stores confirmed tracked-object facts in data; its legacy
    # false_positive DB column is null. Do not apply that rule to arbitrary or
    # malformed notifications. Explicit true always rejects.
    fp = payload.get("false_positive")
    data = payload.get("data", {})
    confirmed_v018 = (
        fp is None
        and isinstance(data, dict)
        and data.get("type") == "object"
        and type(data.get("score")) in (int, float)
        and math.isfinite(data["score"])
        and 0 < data["score"] <= 1
        and data.get("snapshot_clean") is True
        and payload.get("has_snapshot") is True
    )
    if fp is not False and not confirmed_v018:
        return None
    if completed and payload.get("end_time") is None:
        return None
    try:
        start = payload["start_time"]
        end = payload.get("end_time")
        if type(start) not in (int, float) or not math.isfinite(start):
            raise ValueError
        if end is not None and (type(end) not in (int, float) or not math.isfinite(end)):
            raise ValueError
        return EventRef(
            valid_id(payload["id"]),
            payload["camera"],
            "dog",
            datetime.fromtimestamp(start, UTC),
            datetime.fromtimestamp(end, UTC) if end is not None else None,
            payload.get("has_clip") is True,
            payload.get("has_snapshot") is True,
            False,
            payload,
        )
    except (KeyError, ValueError, OverflowError, OSError, TypeError):
        raise FrigateError("invalid_event") from None


class FrigateClient:
    """Explicit none/bearer/basic/session auth, TLS verification and bounded reads.

    Inject httpx.Client/MockTransport for tests. No redirect following; credentials
    cannot be forwarded to another origin. Caller/queue owns finite retry scheduling.
    """

    def __init__(self, settings, client=None):
        self.settings = settings
        self.base = settings.get("FRIGATE_BASE_URL", "").rstrip("/")
        safe_url(self.base)
        self.mode = settings.get("FRIGATE_AUTH_MODE")
        if self.mode not in ("none", "bearer", "basic", "session"):
            raise FrigateError("auth_mode_unconfigured")
        self.cameras = tuple(settings.get("FRIGATE_CAMERA_IDS", ()))
        if len(self.cameras) != 2 or len(set(self.cameras)) != 2:
            raise FrigateError("camera_mapping_unconfigured")
        for camera in self.cameras:
            valid_id(camera)
        self.headers = {}
        self.auth = None
        if self.mode == "bearer":
            token = settings.secrets.get("FRIGATE_TOKEN")
            if not token:
                raise FrigateError("auth_missing")
            self.headers["Authorization"] = "Bearer " + token
        if self.mode in ("basic", "session"):
            user, password = (
                settings.secrets.get(k) for k in ("FRIGATE_USERNAME", "FRIGATE_PASSWORD")
            )
            if not user or not password:
                raise FrigateError("auth_missing")
            if self.mode == "basic":
                self.auth = httpx.BasicAuth(user, password)
        self.client = client or httpx.Client(
            verify=settings.get("FRIGATE_CA_BUNDLE") or True,
            timeout=httpx.Timeout(30, connect=10),
            follow_redirects=False,
        )
        self.owns_client = client is None
        self.logged_in = False

    def close(self):
        if self.owns_client:
            self.client.close()

    def _url(self, path):
        return self.base + ("" if self.base.endswith("/api") else "/api") + path

    @staticmethod
    def _status(status):
        if status in (401, 403):
            raise FrigateError("auth_denied")
        if status in (404, 409, 425):
            raise FrigateError("media_unavailable", retryable=True)
        if status == 410:
            raise FrigateError("media_expired")
        if status == 429 or status >= 500:
            raise FrigateError("source_unavailable", retryable=True)
        if status != 200:
            raise FrigateError("unexpected_status")

    def _login(self):
        try:
            response = self.client.post(
                self._url("/login"),
                json={
                    "user": self.settings.secrets["FRIGATE_USERNAME"],
                    "password": self.settings.secrets["FRIGATE_PASSWORD"],
                },
                timeout=15,
                follow_redirects=False,
            )
            self._status(response.status_code)
            self.logged_in = True
        except httpx.HTTPError:
            raise FrigateError("source_unavailable", retryable=True) from None

    def read(self, path, *, params=None, max_bytes=4_194_304, deadline_seconds=60):
        """Finite streamed read, bounded encoded/decoded bytes and wall duration."""
        if self.mode == "session" and not self.logged_in:
            self._login()
        started = monotonic()
        try:
            with self.client.stream(
                "GET",
                self._url(path),
                params=params,
                headers=self.headers,
                auth=self.auth,
                timeout=30,
                follow_redirects=False,
            ) as response:
                self._status(response.status_code)
                length = response.headers.get("content-length")
                if length is not None and (not length.isdecimal() or int(length) > max_bytes):
                    raise FrigateError("media_byte_limit")
                chunks, count = [], 0
                for chunk in response.iter_bytes(chunk_size=65536):
                    count += len(chunk)
                    if count > max_bytes:
                        raise FrigateError("media_byte_limit")
                    if monotonic() - started > deadline_seconds:
                        raise FrigateError("download_timeout", retryable=True)
                    chunks.append(chunk)
                return b"".join(chunks)
        except httpx.HTTPError:
            raise FrigateError("source_unavailable", retryable=True) from None
        except FrigateError as error:
            if error.code == "auth_denied" and self.mode == "session":
                self.logged_in = False  # next bounded queue attempt may reauthenticate
            raise

    def json(self, path, *, params=None, max_bytes=4_194_304):
        try:
            return json.loads(self.read(path, params=params, max_bytes=max_bytes))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise FrigateError("invalid_json") from None

    def event(self, event_id):
        return self.json("/events/" + valid_id(event_id))

    def events(self, *, after, before, limit=250):
        result = self.json(
            "/events",
            params={
                "cameras": ",".join(self.cameras),
                "labels": "dog",
                "after": after,
                "before": before,
                "limit": limit,
                "sort": "date_desc",
                "include_thumbnails": 0,
            },
            max_bytes=16_777_216,
        )
        if not isinstance(result, list) or len(result) > limit:
            raise FrigateError("invalid_event_page")
        return result

    def snapshot(self, event):
        """Uncropped clean native snapshot; no timestamp/bounding-box overlays."""
        return self.read(
            "/events/" + valid_id(event.event_id) + "/snapshot-clean.webp",
            max_bytes=min(self.settings.get("MAX_CLIP_BYTES", 104857600), 33_554_432),
        )

    def recording_frame(self, event, observed_at):
        """Native recording image at a source UTC timestamp, with no resize request.

        The installed Frigate API decodes the recording at this requested time.
        A matching source snapshot/box can be mapped only after aspect/FOV checks;
        arbitrary later views require a local detector, never a static reused box.
        """
        if event.camera not in self.settings.get("NATIVE_FRAME_CAMERA_IDS", []):
            raise FrigateError("native_sensor_mapping_unverified")
        if (
            event.end_time is None
            or observed_at.tzinfo is None
            or not event.start_time <= observed_at <= event.end_time
        ):
            raise FrigateError("recording_frame_time_invalid")
        if event.camera not in self.cameras:
            raise FrigateError("unselected_camera")
        return self.read(
            f"/{valid_id(event.camera)}/recordings/{observed_at.timestamp():.6f}/snapshot.png",
            max_bytes=33_554_432,
        )

    def clip(self, event, output: Path):
        """Download a finite whole clip. Long events require an explicit useful window."""
        if event.end_time is None:
            raise FrigateError("event_in_progress", retryable=True)
        if (event.end_time - event.start_time).total_seconds() > self.settings.get(
            "MAX_CLIP_SECONDS", 60
        ):
            raise FrigateError("clip_duration_limit")
        data = self.read(
            "/events/" + valid_id(event.event_id) + "/clip.mp4",
            max_bytes=self.settings.get("MAX_CLIP_BYTES", 104857600),
        )
        if output.exists() or output.is_symlink():
            raise FrigateError("media_destination_exists")
        with output.open("xb") as handle:
            handle.write(data)
        output.chmod(0o600)
        return output

    def clip_window(self, event, output: Path, *, start_time, end_time):
        """Fetch an explicit bounded recording window within a completed event.

        Frigate remuxes at keyframes; requested start is not certified clip origin.
        Verify recording timestamps before using VideoDecoder for geometry mapping.
        Prefer windows around snapshot_frame_time for long tracks, retaining the
        original full event metadata. This endpoint is not a substitute for boxes.
        """
        if event.end_time is None:
            raise FrigateError("event_in_progress", retryable=True)
        if start_time.tzinfo is None or end_time.tzinfo is None:
            raise FrigateError("clip_time_unverified")
        if not event.start_time <= start_time < end_time <= event.end_time:
            raise FrigateError("clip_window_outside_event")
        if (end_time - start_time).total_seconds() > self.settings.get("MAX_CLIP_SECONDS", 60):
            raise FrigateError("clip_duration_limit")
        if event.camera not in self.cameras:
            raise FrigateError("unselected_camera")
        path = f"/{valid_id(event.camera)}/start/{start_time.timestamp():.6f}/end/{end_time.timestamp():.6f}/clip.mp4"
        data = self.read(path, max_bytes=self.settings.get("MAX_CLIP_BYTES", 104857600))
        if output.exists() or output.is_symlink():
            raise FrigateError("media_destination_exists")
        with output.open("xb") as handle:
            handle.write(data)
        output.chmod(0o600)
        return output
