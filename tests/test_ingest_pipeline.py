import io
import json
import subprocess
from datetime import UTC, datetime, timedelta

import httpx
import numpy as np
import pytest
from PIL import Image

from dog_art.clock import FrozenClock
from dog_art.frigate import EventIngestor, FrigateClient, FrigateError, PollReconciler, parse_event
from dog_art.settings import Settings
from dog_art.storage import Store
from dog_art.vision import (
    CropExtractor,
    DecodedFrame,
    MediaError,
    TrackSample,
    VideoDecoder,
    decode_image,
    snapshot_sample,
)

NOW = datetime(2026, 10, 22, 16, tzinfo=UTC)


def settings(**kwargs):
    return Settings(
        {
            "FRIGATE_BASE_URL": "http://frigate.test:5000",
            "FRIGATE_AUTH_MODE": "none",
            "FRIGATE_CAMERA_IDS": ["backyard_east", "driveway_ptz"],
            "MIN_DOG_CROP_EDGE_PX": 10,
            "DAY_TIMEZONE": "America/New_York",
            **kwargs,
        }
    )


def event(key="synthetic-1", **kwargs):
    return {
        "id": key,
        "camera": "backyard_east",
        "label": "dog",
        "false_positive": False,
        "start_time": NOW.timestamp() - 100,
        "end_time": NOW.timestamp() - 1,
        "has_clip": True,
        "has_snapshot": True,
        "data": {},
        **kwargs,
    }


def test_filter_dedup_notifications_restart(tmp_path):
    dbpath = tmp_path / "state.sqlite"
    store = Store(dbpath)
    ingest = EventIngestor(store, settings(), FrozenClock(NOW))
    for phase in ("new", "update", "end", "end"):
        ingest.ingest_notification(
            {
                "type": phase,
                "after": event(end_time=None if phase != "end" else NOW.timestamp() - 1),
            }
        )
    ingest.ingest_notification({"type": "update", "after": event(end_time=None)})
    store.close()
    store = Store(dbpath)
    ingest = EventIngestor(store, settings(), FrozenClock(NOW))
    ingest.record(event())
    assert store.db.execute("SELECT count(*) FROM events").fetchone()[0] == 1
    assert store.db.execute("SELECT count(*) FROM jobs WHERE kind='extract'").fetchone()[0] == 1
    assert store.db.execute("SELECT end_time FROM events").fetchone()[0] is not None
    for payload in (
        event(label="person"),
        event(camera="other_camera"),
        event(false_positive=True),
        event(false_positive=None),
    ):
        assert ingest.record(payload) is None
    assert ingest.record(event("synthetic-ptz", camera="driveway_ptz"))
    assert parse_event(event(end_time=None), ingest.cameras) is None
    with pytest.raises(FrigateError, match="invalid_event_id"):
        parse_event(event("../../escape"), ingest.cameras)


@pytest.mark.parametrize("mode", ["none", "bearer", "basic", "session"])
def test_explicit_auth_modes(mode):
    requests = []
    secret = {
        "FRIGATE_TOKEN": "seed-token",
        "FRIGATE_USERNAME": "seed-user",
        "FRIGATE_PASSWORD": "seed-password",
    }

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/login":
            assert json.loads(request.content) == {"user": "seed-user", "password": "seed-password"}
            return httpx.Response(200, headers={"set-cookie": "frigate_token=seed-session; Path=/"})
        return httpx.Response(200, json=event())

    client = FrigateClient(
        Settings({**settings().values, "FRIGATE_AUTH_MODE": mode}, secret),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.event("synthetic-1")["label"] == "dog"
    request = requests[-1]
    if mode == "bearer":
        assert request.headers["authorization"] == "Bearer seed-token"
    elif mode == "basic":
        assert request.headers["authorization"].startswith("Basic ")
    elif mode == "session":
        assert "seed-session" in request.headers["cookie"]
    else:
        assert "authorization" not in request.headers


@pytest.mark.parametrize(
    "status,code,retry",
    [
        (401, "auth_denied", False),
        (403, "auth_denied", False),
        (404, "media_unavailable", True),
        (410, "media_expired", False),
        (503, "source_unavailable", True),
        (302, "unexpected_status", False),
    ],
)
def test_http_fault_codes_redact(status, code, retry):
    client = FrigateClient(
        settings(),
        httpx.Client(
            transport=httpx.MockTransport(lambda req: httpx.Response(status, text="seed-secret"))
        ),
    )
    with pytest.raises(FrigateError) as caught:
        client.event("synthetic-1")
    assert str(caught.value) == code
    assert caught.value.retryable is retry
    assert "seed-secret" not in str(caught.value)


def test_download_bytes_json_and_clip_duration(tmp_path):
    def handler(request):
        if request.url.path.endswith("snapshot-clean.webp"):
            return httpx.Response(200, content=b"x" * 100)
        return httpx.Response(200, content=b"not json")

    config = settings(MAX_CLIP_BYTES=20)
    client = FrigateClient(config, httpx.Client(transport=httpx.MockTransport(handler)))
    ref = parse_event(event(), config["FRIGATE_CAMERA_IDS"])
    with pytest.raises(FrigateError, match="media_byte_limit"):
        client.snapshot(ref)
    with pytest.raises(FrigateError, match="invalid_json"):
        client.event(ref.event_id)
    with pytest.raises(FrigateError, match="clip_duration_limit"):
        client.clip(ref, tmp_path / "test.mp4")
    assert not (tmp_path / "test.mp4").exists()


def test_paginated_reconcile_overlap_ties_outage_and_pending(tmp_path):
    payloads = [event("p-" + str(i), start_time=NOW.timestamp() - 1000 + i // 3) for i in range(21)]
    pending = event("long-track", start_time=NOW.timestamp() - 5000, end_time=None)
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path == "/api/events/long-track":
            return httpx.Response(200, json={**pending, "end_time": NOW.timestamp() - 1})
        q = request.url.params
        after, before, limit = float(q["after"]), float(q["before"]), int(q["limit"])
        assert q["sort"] == "date_desc" and q["labels"] == "dog"
        rows = sorted(
            [p for p in payloads if after < p["start_time"] < before],
            key=lambda p: p["start_time"],
            reverse=True,
        )[:limit]
        return httpx.Response(200, json=rows)

    store = Store(tmp_path / "state.sqlite")
    ingest = EventIngestor(store, settings(), FrozenClock(NOW))
    ingest.record(pending)
    store.db.execute(
        "INSERT INTO meta VALUES('frigate_poll_cursor',?)", (str(NOW.timestamp() - 3600),)
    )
    poll = PollReconciler(
        FrigateClient(settings(), httpx.Client(transport=httpx.MockTransport(handler))),
        ingest,
        page_size=4,
    )
    assert poll.reconcile() == 21
    assert store.db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 22
    assert len(calls) > 5
    poll.reconcile()
    assert store.db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 22


def test_poll_failure_keeps_cursor_and_retry_dedups(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    ingest = EventIngestor(store, settings(), FrozenClock(NOW))

    class Broken:
        def events(self, **kwargs):
            raise FrigateError("source_unavailable", retryable=True)

    poll = PollReconciler(Broken(), ingest)
    with pytest.raises(FrigateError):
        poll.reconcile()
    assert store.db.execute("SELECT value FROM meta WHERE key=?", (poll.CURSOR,)).fetchone() is None

    class Saturated:
        def events(self, **kwargs):
            return [event(str(i)) for i in range(kwargs["limit"])]

    with pytest.raises(FrigateError, match="pagination_timestamp_saturated"):
        PollReconciler(Saturated(), ingest, page_size=2, max_page_size=4).reconcile()
    assert store.db.execute("SELECT value FROM meta WHERE key=?", (poll.CURSOR,)).fetchone() is None


def test_media_decode_pixel_malformed_and_motion_geometry(tmp_path):
    with pytest.raises(MediaError, match="invalid_image"):
        decode_image(b"not an image")
    buffer = io.BytesIO()
    Image.new("RGB", (100, 100)).save(buffer, format="PNG")
    with pytest.raises(MediaError, match="image_pixel_limit"):
        decode_image(buffer.getvalue(), max_pixels=100)
    image = Image.fromarray(
        np.random.default_rng(4).integers(0, 256, (1080, 1920, 3), dtype=np.uint8)
    )
    ref = parse_event(event(), settings()["FRIGATE_CAMERA_IDS"])
    first, second = NOW - timedelta(seconds=90), NOW - timedelta(seconds=80)
    frames = (DecodedFrame(image, first), DecodedFrame(image, second))
    samples = (
        TrackSample("dog-a", first, (100, 100, 300, 400), (1920, 1080), True),
        TrackSample("dog-a", second, (900, 100, 1100, 400), (1920, 1080), True),
        TrackSample("dog-b", first, (500, 100, 700, 400), (1920, 1080), True),
    )
    observations, rejected = CropExtractor(settings(), min_sharpness=5).extract(
        ref, frames, samples, tmp_path
    )
    assert rejected == ()
    assert len(observations) == 2
    assert len(observations[0].crops) == 2
    boxes = [crop.box for crop in observations[0].crops]
    assert boxes[0] != boxes[1]  # moving PTZ box must follow its own timestamp
    for observation in observations:
        assert observation.visibility == "full_body"
        assert all(c.source_size == (1920, 1080) and c.full_body for c in observation.crops)
        assert len({c.sha256 for c in observation.crops}) == len(observation.crops)
    repeated, _ = CropExtractor(settings()).extract(ref, frames, samples, tmp_path)
    assert [o.observation_id for o in repeated] == [o.observation_id for o in observations]


def test_resolution_scaling_overlap_blur_occlusion_abstain(tmp_path):
    ref = parse_event(event(), settings()["FRIGATE_CAMERA_IDS"])
    timestamp = NOW - timedelta(seconds=50)
    image = Image.new("RGB", (1920, 1080), "gray")
    frame = DecodedFrame(image, timestamp)
    extractor = CropExtractor(settings(), min_sharpness=1)
    sample = TrackSample("a", timestamp, (30, 30, 100, 100), (640, 360), True)
    observations, rejected = extractor.extract(ref, (frame,), (sample,), tmp_path)
    assert not observations and rejected[0][1] == "blurred"
    for replacement, reason in (
        (TrackSample("a", timestamp, (30, 30, 100, 100), (640, 480)), "source_aspect_mismatch"),
        (
            TrackSample("a", timestamp + timedelta(seconds=1), sample.box, sample.source_size),
            "frame_time_mismatch",
        ),
        (
            TrackSample("a", timestamp, sample.box, sample.source_size, True, True),
            "occluded_or_clipped",
        ),
    ):
        obs, rejected = extractor.extract(ref, (frame,), (replacement,), tmp_path)
        assert not obs and rejected[0][1] == reason
    other = TrackSample("b", timestamp, (35, 35, 110, 110), (640, 360), True)
    obs, rejected = extractor.extract(ref, (frame,), (sample, other), tmp_path)
    assert not obs and {r[1] for r in rejected} == {"ambiguous_overlapping_dogs"}
    unknown = TrackSample("a", timestamp, sample.box, sample.source_size)
    scaled, _ = CropExtractor(settings()).extract(ref, (frame,), (unknown,), tmp_path)
    assert scaled[0].crops[0].box == (73, 73, 317, 317)
    assert not scaled[0].crops[0].full_body
    assert scaled[0].visibility == "unknown"


def test_snapshot_geometry_xywh_exact_timestamp():
    timestamp = NOW.timestamp() - 50
    ref = parse_event(
        event(
            data={
                "box": [0.1, 0.2, 0.2, 0.3],
                "snapshot_frame_time": timestamp,
                "snapshot_clean": True,
            }
        ),
        settings()["FRIGATE_CAMERA_IDS"],
    )
    sample = snapshot_sample(ref, Image.new("RGB", (1920, 1080)))
    assert sample.box == pytest.approx((192, 216, 576, 540))
    assert sample.observed_at.timestamp() == timestamp
    assert not sample.full_body
    bad = parse_event(event(data={"box": [0.1, 0.2, 0.2, 0.3]}), settings()["FRIGATE_CAMERA_IDS"])
    with pytest.raises(MediaError, match="clean_snapshot_unverified"):
        snapshot_sample(bad, Image.new("RGB", (1920, 1080)))


def test_decoder_pts_limits_faults(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"synthetic")
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        assert kwargs["timeout"] == 30
        assert "FRIGATE_TOKEN" not in kwargs["env"]
        if "-show_entries" in args:
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps(
                    {"streams": [{"width": 20, "height": 10}], "format": {"duration": "10"}}
                ).encode(),
                b"",
            )
        return subprocess.CompletedProcess(args, 0, b"x" * 600, b"showinfo pts_time:2.04")

    result = VideoDecoder(runner=runner).frame(path, clip_start_time=NOW, offset_seconds=2)
    assert result.observed_at == NOW + timedelta(seconds=2.04)
    assert result.image.size == (20, 10)
    assert "file,pipe" in calls[1] and "-nostdin" in calls[1]
    with pytest.raises(MediaError, match="clip_pixel_limit"):
        VideoDecoder(runner=runner, max_pixels=50).frame(
            path, clip_start_time=NOW, offset_seconds=2
        )
    with pytest.raises(MediaError, match="clip_duration_limit"):
        VideoDecoder(runner=runner, max_seconds=5).frame(
            path, clip_start_time=NOW, offset_seconds=2
        )

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("ffprobe", 30)

    with pytest.raises(MediaError, match="decoder_timeout"):
        VideoDecoder(runner=timeout).frame(path, clip_start_time=NOW, offset_seconds=2)


def test_delayed_media_retry_budget_and_auth_expiry(tmp_path):
    store = Store(tmp_path / "queue.sqlite")
    config = settings(READ_RETRY_ATTEMPTS=2)
    ingest = EventIngestor(store, config, FrozenClock(NOW))
    ingest.record(event())
    now = NOW.timestamp()
    first = store.claim(now, kinds=["extract"])
    store.finish(
        first["job_id"], first["lease_token"], error_code="media_unavailable", retry_at=now + 5
    )
    assert store.claim(now + 4, kinds=["extract"]) is None
    second = store.claim(now + 5, kinds=["extract"])
    store.finish(
        second["job_id"], second["lease_token"], error_code="media_unavailable", retry_at=now + 10
    )
    assert store.claim(now + 10, kinds=["extract"]) is None
    assert store.status()["jobs"] == {"exhausted": 1}
    requests = []

    def handler(request):
        requests.append(request.url.path)
        if request.url.path == "/api/login":
            return httpx.Response(200, headers={"set-cookie": "frigate_token=seed; Path=/"})
        return httpx.Response(401)

    client = FrigateClient(
        Settings(
            {**config.values, "FRIGATE_AUTH_MODE": "session"},
            {"FRIGATE_USERNAME": "seed", "FRIGATE_PASSWORD": "seed"},
        ),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    for _ in range(2):
        with pytest.raises(FrigateError, match="auth_denied"):
            client.event("synthetic-1")
    assert requests == ["/api/login", "/api/events/synthetic-1"] * 2


def test_expired_pending_audits_once_and_source_failure_does_not_advance(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    ingest = EventIngestor(store, settings(), FrozenClock(NOW))
    ingest.record(event(end_time=None))

    class Expired:
        def events(self, **kwargs):
            return []

        def event(self, event_id):
            raise FrigateError("media_unavailable", retryable=True)

    poll = PollReconciler(Expired(), ingest)
    poll.reconcile()
    poll.reconcile()
    assert (
        store.db.execute("SELECT count(*) FROM audit WHERE code='source_event_expired'").fetchone()[
            0
        ]
        == 1
    )
    assert store.db.execute("SELECT end_time FROM events").fetchone()[0] is None


def test_native_crop_privacy_integrity_and_provenance(tmp_path):
    ref = parse_event(event(), settings()["FRIGATE_CAMERA_IDS"])
    timestamp = NOW - timedelta(seconds=50)
    frame = DecodedFrame(Image.new("RGB", (400, 200)), timestamp)
    sample = TrackSample(
        "local-dog", timestamp, (50, 50, 100, 100), (400, 200), provenance="artwork"
    )
    with pytest.raises(MediaError, match="non_camera_provenance"):
        CropExtractor(settings()).extract(ref, (frame,), (sample,), tmp_path)
    sample = TrackSample("local-dog", timestamp, (50, 50, 100, 100), (400, 200))
    extractor = CropExtractor(settings())
    observations, _ = extractor.extract(ref, (frame,), (sample,), tmp_path)
    crop = observations[0].crops[0]
    assert crop.path.stat().st_mode & 0o777 == 0o600
    crop.path.write_bytes(b"corrupt")
    with pytest.raises(MediaError, match="crop_integrity_failure"):
        extractor.model_input(crop)


def test_recording_window_bounds_for_long_event(tmp_path):
    requested = []

    def handler(request):
        requested.append(request.url.path)
        return httpx.Response(200, content=b"synthetic-mp4")

    client = FrigateClient(settings(), httpx.Client(transport=httpx.MockTransport(handler)))
    ref = parse_event(event(start_time=NOW.timestamp() - 3600), settings()["FRIGATE_CAMERA_IDS"])
    with pytest.raises(FrigateError, match="clip_duration_limit"):
        client.clip(ref, tmp_path / "whole.mp4")
    start, end = NOW - timedelta(seconds=50), NOW - timedelta(seconds=10)
    client.clip_window(ref, tmp_path / "window.mp4", start_time=start, end_time=end)
    assert "/backyard_east/start/" in requested[0]
    assert (tmp_path / "window.mp4").read_bytes() == b"synthetic-mp4"
    with pytest.raises(FrigateError, match="clip_window_outside_event"):
        client.clip_window(ref, tmp_path / "invalid.mp4", start_time=end, end_time=NOW)


def test_frigate_v018_confirmed_object_with_null_legacy_field():
    from dog_art.frigate.client import parse_event

    payload = {
        "id": "1792703484.467397-sanitized",
        "camera": "driveway_ptz",
        "label": "dog",
        "start_time": 1792703484.467397,
        "end_time": 1792703490.463379,
        "has_clip": True,
        "has_snapshot": True,
        "false_positive": None,
        "data": {"type": "object", "score": 0.78, "snapshot_clean": True},
    }
    assert parse_event(payload, ("driveway_ptz", "backyard_east")) is not None
    payload["false_positive"] = True
    assert parse_event(payload, ("driveway_ptz", "backyard_east")) is None
    payload["false_positive"] = None
    payload["data"]["type"] = "api"
    assert parse_event(payload, ("driveway_ptz", "backyard_east")) is None


def test_small_real_crop_is_retained_without_size_floor(tmp_path):
    raw = event()
    ref = parse_event(raw, {"backyard_east"})
    when = ref.start_time
    image = Image.new("RGB", (100, 100), "gray")
    sample = TrackSample("tiny", when, (40, 40, 42, 42), (100, 100), full_body=False)
    # Legacy settings cannot reintroduce the removed size cutoff.
    extractor = CropExtractor(settings(MIN_DOG_CROP_EDGE_PX=1000))
    observations, rejected = extractor.extract(
        ref, (DecodedFrame(image, when),), (sample,), tmp_path
    )
    assert len(observations) == 1 and rejected == ()
    assert not observations[0].crops[0].full_body
    assert min(Image.open(observations[0].crops[0].path).size) < 10
