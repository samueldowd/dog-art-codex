"""Durable event ingestion and start-time reconciliation without silent page gaps."""

import json
import math
from zoneinfo import ZoneInfo

from .client import FrigateError, parse_event


class EventIngestor:
    """SQLite event uniqueness and one extract job per completed Frigate track.

    ingest_notification accepts real MQTT-shaped new/update/end envelopes but does
    not own a broker connection. Polling remains the durable source/reconnect path.
    """

    def __init__(self, store, settings, clock):
        self.store, self.settings, self.clock = store, settings, clock
        self.cameras = tuple(settings.get("FRIGATE_CAMERA_IDS", ()))

    def record(self, payload, *, db=None):
        event = parse_event(payload, self.cameras, completed=False)
        if event is None:
            return None
        if db is None:
            with self.store.transaction() as conn:
                return self.record(payload, db=conn)
        old = db.execute(
            "SELECT camera,start_time,end_time FROM events WHERE event_id=?", (event.event_id,)
        ).fetchone()
        if old and (
            old["camera"] != event.camera or old["start_time"] != event.start_time.timestamp()
        ):
            raise FrigateError("event_identity_changed")
        # A replay of a stale update cannot reopen a completed event.
        if old and old["end_time"] is not None and event.end_time is None:
            return event
        db.execute(
            "INSERT INTO events(event_id,camera,start_time,end_time,payload) VALUES(?,?,?,?,?) "
            "ON CONFLICT(event_id) DO UPDATE SET end_time=excluded.end_time,payload=excluded.payload",
            (
                event.event_id,
                event.camera,
                event.start_time.timestamp(),
                event.end_time.timestamp() if event.end_time else None,
                json.dumps(payload, sort_keys=True, allow_nan=False),
            ),
        )
        if event.end_time is not None:
            self.store.enqueue(
                "extract",
                "extract:" + event.event_id,
                {"event_id": event.event_id},
                self.clock.now().timestamp(),
                max_attempts=self.settings.get("READ_RETRY_ATTEMPTS", 3),
                db=db,
            )
        return event

    def ingest_notification(self, envelope):
        if not isinstance(envelope, dict) or envelope.get("type") not in ("new", "update", "end"):
            raise FrigateError("invalid_notification")
        return self.record(envelope.get("after"))


class PollReconciler:
    """Page backward by strict source start_time, replay equal-time boundaries.

    Cursor moves only after complete enumeration and pending-event refresh. A
    saturated equal timestamp grows its finite page limit, then fails visibly
    without advancing. Existing incomplete events are re-read by ID so long tracks
    and an outage longer than overlap cannot fall out of coverage.
    """

    CURSOR = "frigate_poll_cursor"

    def __init__(self, client, ingestor, *, page_size=250, max_page_size=10000, max_pages=1000):
        self.client, self.ingestor = client, ingestor
        self.store, self.settings, self.clock = ingestor.store, ingestor.settings, ingestor.clock
        self.page_size, self.max_page_size, self.max_pages = page_size, max_page_size, max_pages
        if not (0 < page_size <= max_page_size and max_pages > 0):
            raise ValueError("positive bounded pagination required")

    def _page_events(self, after, before):
        limit, pages, seen = self.page_size, 0, set()
        while pages < self.max_pages:
            page = self.client.events(after=after, before=before, limit=limit)
            pages += 1
            times = []
            for payload in page:
                if not isinstance(payload, dict):
                    raise FrigateError("invalid_event_page")
                value = payload.get("start_time")
                if (
                    type(value) not in (int, float)
                    or not math.isfinite(value)
                    or not after < value < before
                ):
                    raise FrigateError("invalid_event_page")
                times.append(value)
            if times != sorted(times, reverse=True):
                raise FrigateError("unordered_event_page")
            for payload in page:
                key = payload.get("id")
                if key not in seen:
                    seen.add(key)
                    yield payload
            if len(page) < limit:
                return
            oldest = min(times)
            if max(times) == oldest:
                if limit >= self.max_page_size:
                    raise FrigateError("pagination_timestamp_saturated")
                limit = min(limit * 2, self.max_page_size)
                continue
            # Include boundary timestamp again, rather than skipping other objects
            # at that exact timestamp. nextafter respects strict Frigate `< before`.
            before = math.nextafter(oldest, math.inf)
            limit = self.page_size
        raise FrigateError("pagination_limit")

    def reconcile(self):
        now = self.clock.now()
        row = self.store.db.execute("SELECT value FROM meta WHERE key=?", (self.CURSOR,)).fetchone()
        if row:
            after = float(row["value"]) - self.settings.get("EVENT_RECONCILE_OVERLAP_SECONDS", 120)
        else:
            if self.settings.get("EVENT_INITIAL_BACKFILL", "today") != "today":
                raise FrigateError("unsupported_initial_backfill")
            local = now.astimezone(ZoneInfo(self.settings.get("DAY_TIMEZONE", "America/New_York")))
            after = math.nextafter(
                local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp(), -math.inf
            )
        count = 0
        # Partial records are intentionally durable even if a later page fails;
        # dedup allows safe replay while the cursor remains at the prior checkpoint.
        for payload in self._page_events(after, math.nextafter(now.timestamp(), math.inf)):
            if self.ingestor.record(payload):
                count += 1
        pending = self.store.db.execute(
            "SELECT event_id FROM events WHERE end_time IS NULL AND NOT EXISTS "
            "(SELECT 1 FROM meta WHERE key='frigate_expired:' || events.event_id)"
        ).fetchall()
        for row in pending:
            try:
                self.ingestor.record(self.client.event(row["event_id"]))
            except FrigateError as error:
                if error.code not in ("media_unavailable", "media_expired"):
                    raise
                with self.store.transaction() as db:
                    # Keep the original event evidence; a tombstone prevents an
                    # expired pending event consuming every subsequent poll.
                    db.execute(
                        "INSERT OR IGNORE INTO meta VALUES(?,?)",
                        ("frigate_expired:" + row["event_id"], str(now.timestamp())),
                    )
                    self.store.audit(
                        "source_event_expired",
                        {"event_id": row["event_id"]},
                        now.timestamp(),
                        db=db,
                    )
        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (self.CURSOR, str(now.timestamp())),
            )
        return count
