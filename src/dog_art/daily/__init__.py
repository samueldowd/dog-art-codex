"""Persistent local-calendar membership, immutable revisions and publish ordering.

The application-wide publication lock is an advisory POSIX file lock shared by
rollover, composition finalization and Publisher. All network operations must be
bounded, and publishers MUST call guard.revalidate() immediately before replacing
the remote owned image. No SQLite transaction is held during rendering/network.
"""

import fcntl
import hashlib
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..collage import (
    CollageRenderer,
    ImmutableArchiveError,
    load_revision,
    revision_payload,
    write_receipt,
)
from ..contracts import CollageRevision, utc
from ..safety import disk_guard, owned_path, sha256


class PortraitPendingError(ValueError):
    """Accepted membership is retained; a validated portrait is not ready."""


class StalePublication(ValueError):
    """Publication is obsolete by wall date, generation, revision or content."""


class PublicationBusyError(TimeoutError):
    """The bounded wait for the shared publication barrier expired."""


@dataclass(frozen=True)
class DayState:
    day: str
    generation: str
    revision: int
    dog_ids: tuple[str, ...]


_thread_locks = {}
_thread_lock_guard = threading.Lock()


@contextmanager
def application_lock(path: Path, *, timeout: float = 15):
    """Cross-process and cross-thread barrier; fail boundedly on lock contention."""
    with _thread_lock_guard:
        local_lock = _thread_locks.setdefault(str(path), threading.Lock())
    deadline = time.monotonic() + timeout
    if not local_lock.acquire(timeout=timeout):
        raise PublicationBusyError("publication barrier busy; retry boundedly")
    fd = None
    try:
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise PublicationBusyError("publication barrier busy; retry boundedly")
                time.sleep(min(0.02, max(0, deadline - time.monotonic())))
        yield
    finally:
        if fd is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        local_lock.release()


class PublicationGuard:
    """A held barrier whose revalidate() is mandatory just before SMB replace.

    The guard is valid only inside DailyManager.publication_guard(). Its clock
    check establishes a missed new day and queues its blank before rejecting
    yesterday's pending upload. Final replacement itself must be a bounded call.
    A clock crossing during that call is corrected by the waiting rollover.
    """

    def __init__(self, manager, revision):
        self.manager, self.revision = manager, revision
        self.active = True

    def revalidate(self, *, db=None):
        """Check publication against current inputs, optionally inside receipt tx.

        The db form never opens a transaction or renders rollover state. The
        publisher uses it inside its receipt write transaction, serializing the
        last approval/readiness check with committing the verified receipt.
        """
        if not self.active:
            raise StalePublication("publication guard is no longer held")
        m, r = self.manager, self.revision
        if db is None:
            current = m._rollover_locked()
            if current.day != r.day:
                raise StalePublication("wall date changed; new-day output queued")
            with m.store.transaction() as connection:
                return self.revalidate(db=connection)
        if m._today() != r.day:
            raise StalePublication("wall date changed before publication receipt")
        current = m._normalize_locked(r.day, db)
        row = db.execute(
            "SELECT * FROM collages WHERE day=? AND revision=?", (r.day, r.revision)
        ).fetchone()
        outbox = db.execute(
            "SELECT * FROM outbox WHERE day=? AND revision=?", (r.day, r.revision)
        ).fetchone()
        reset_waiting = (
            db.execute(
                "SELECT 1 FROM outbox WHERE day=? AND generation=? AND revision=0 AND state='reset_pending'",
                (current.day, current.generation),
            ).fetchone()
            is not None
        )
        bound = (
            current.generation == r.generation
            and row is not None
            and outbox is not None
            and row["generation"] == r.generation
            and outbox["generation"] == r.generation
            and row["sha256"] == r.sha256
            and outbox["sha256"] == r.sha256
            and row["path"] == str(r.output_path)
        )
        reset = (
            bound
            and r.revision == 0
            and r.dog_ids == ()
            and r.portrait_hashes == ()
            and r.pending_dog_ids == ()
            and r.portrait_policy == "all_accepted"
            and outbox["state"] == "reset_pending"
            and not m._has_verified_publication(current, db)
            and json.loads(row["payload"])["dog_ids"] == []
            and json.loads(row["payload"])["portrait_hashes"] == []
        )
        empty_retry = (
            bound
            and r.revision == 0
            and r.dog_ids == ()
            and r.portrait_hashes == ()
            and r.pending_dog_ids == ()
            and r.portrait_policy == "all_accepted"
            and outbox["state"] == "published"
            and not m._has_verified_full_publication(current, db)
            and json.loads(row["payload"])["dog_ids"] == []
            and json.loads(row["payload"])["portrait_hashes"] == []
        )
        metadata = m._inputs_metadata(current, db)
        ready_ids = (
            tuple(item[0] for item in metadata["ready"])
            if m.portrait_policy == "approved_only"
            else current.dog_ids
        )
        pending_ids = tuple(metadata["pending"]) if m.portrait_policy == "approved_only" else ()
        desired = (
            bound
            and not reset_waiting
            and (r.revision != 0 or empty_retry)
            and current.revision == r.revision
            and ready_ids == r.dog_ids
            and pending_ids == r.pending_dog_ids
            and r.portrait_policy == (m.portrait_policy if r.revision else "all_accepted")
            and outbox["state"] in {"pending", "publishing", "published"}
        )
        if desired and not (reset or empty_retry):
            _, hashes, checked_pending = m._portrait_inputs(current, db)
            desired = hashes == r.portrait_hashes and checked_pending == r.pending_dog_ids
        if not (reset or desired):
            raise StalePublication("generation/revision/membership is obsolete or reset pending")
        if sha256(r.output_path) != r.sha256:
            raise StalePublication("local archived bytes changed")
        if m._today() != r.day:
            raise StalePublication("wall date changed during publication validation")
        return r


class DailyManager:
    """Resolve event timestamps into durable day sets and immutable RGB collages.

    Integration: record_sighting(canonical_id, observation timestamps), then build
    each returned day according to the configured portrait policy. DayState
    always retains all accepted membership; approved_only CollageRevision stores
    ready members and explicit pending_dog_ids. Missing/corrupt approved inputs
    still hold composition. Startup/timer reconciliation preserves reset priority.
    """

    def __init__(self, store, settings, clock):
        self.store, self.settings, self.clock = store, settings, clock
        self.root = Path(settings["APP_DATA_ROOT"])
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock_path = owned_path(self.root, "locks/publication.lock", create_parent=True)
        self.zone = ZoneInfo(settings.get("DAY_TIMEZONE", "America/New_York"))
        self.renderer = CollageRenderer(settings)
        self.portrait_policy = settings.get("COLLAGE_PORTRAIT_POLICY", "all_accepted")
        if self.portrait_policy not in {"all_accepted", "approved_only"}:
            raise ValueError("unsupported collage portrait policy")

    def _today(self):
        return utc(self.clock.now()).astimezone(self.zone).date().isoformat()

    def _day(self, observed_at):
        return utc(observed_at).astimezone(self.zone).date().isoformat()

    @staticmethod
    def _validate_day(day):
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError("ISO calendar date required")
        return day

    def _ensure_day(self, day, db):
        db.execute(
            "INSERT OR IGNORE INTO days(day,generation,created_at) VALUES(?,?,?)",
            (day, uuid.uuid4().hex, utc(self.clock.now()).timestamp()),
        )
        return db.execute("SELECT * FROM days WHERE day=?", (day,)).fetchone()

    def _state(self, day, db):
        row = db.execute("SELECT * FROM days WHERE day=?", (day,)).fetchone()
        if row is None:
            raise ValueError("unknown day")
        ids = tuple(
            r[0]
            for r in db.execute("SELECT dog_id FROM membership WHERE day=? ORDER BY dog_id", (day,))
        )
        return DayState(day, row["generation"], row["desired_revision"], ids)

    def _queue(self, state, db):
        self.store.enqueue(
            "collage",
            f"collage:{state.generation}:{state.revision}",
            {"day": state.day, "generation": state.generation, "revision": state.revision},
            utc(self.clock.now()).timestamp(),
            db=db,
        )
        # Old pending work may still finish locally, but is never publishable.
        db.execute(
            "UPDATE outbox SET state='obsolete' WHERE state IN ('pending','publishing') AND (day != ? OR generation != ? OR revision != ?)",
            (self._today(), state.generation, state.revision),
        ) if state.day == self._today() else None

    def _normalize_locked(self, day, db):
        before = self._state(day, db)
        rows = db.execute("SELECT * FROM membership WHERE day=?", (day,)).fetchall()
        merged = {}
        for row in rows:
            canonical = self.store.canonical(row["dog_id"], db=db)
            accepted = (
                db.execute("SELECT state FROM dogs WHERE dog_id=?", (canonical,)).fetchone()[0]
                == "accepted"
            )
            if not accepted:
                continue
            old = merged.get(canonical)
            merged[canonical] = (
                min(row["first_seen"], old[0]) if old else row["first_seen"],
                max(row["last_seen"], old[1]) if old else row["last_seen"],
            )
        if tuple(sorted(merged)) != before.dog_ids:
            db.execute("DELETE FROM membership WHERE day=?", (day,))
            db.executemany(
                "INSERT INTO membership VALUES(?,?,?,?)",
                [(day, k, v[0], v[1]) for k, v in sorted(merged.items())],
            )
            db.execute("UPDATE days SET desired_revision=desired_revision+1 WHERE day=?", (day,))
            self.store.audit(
                "membership_canonicalized",
                {"day": day, "before": before.dog_ids, "after": sorted(merged)},
                utc(self.clock.now()).timestamp(),
                db=db,
            )
            self._queue(self._state(day, db), db)
        return self._sync_inputs_locked(self._state(day, db), db)

    def _inputs_metadata(self, state, db):
        """Describe selected approvals without treating bad approved files as pending."""
        ready, pending = [], []
        for dog_id in state.dog_ids:
            row = db.execute(
                "SELECT recipe_key,path,sha256 FROM portraits WHERE dog_id=? AND state='validated' ORDER BY rowid LIMIT 1",
                (dog_id,),
            ).fetchone()
            if row is None:
                pending.append(dog_id)
            else:
                ready.append((dog_id, row["recipe_key"], row["path"], row["sha256"]))
        return {
            "policy": self.portrait_policy,
            "members": list(state.dog_ids),
            "ready": ready,
            "pending": pending,
            "layout": {
                key: self.settings.get(key, default)
                for key, default in (
                    ("COLLAGE_WIDTH", 1920),
                    ("COLLAGE_HEIGHT", 1080),
                    ("COLLAGE_BACKGROUND", "#F3EBDD"),
                    ("COLLAGE_LAYOUT", "scattered"),
                    ("COLLAGE_MARGIN_PX", 40),
                    ("COLLAGE_MIN_DOG_HEIGHT_PX", 120),
                )
            },
        }

    def _sync_inputs_locked(self, state, db):
        """Bind each revision to approvals/policy even when no new sighting arrives."""
        inputs = self._inputs_metadata(state, db)
        signature = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
        key = f"collage_inputs:{state.generation}"
        old = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        previous = json.loads(old[0]) if old else None
        if previous and previous["signature"] == signature:
            return state
        existing = db.execute(
            "SELECT payload FROM collages WHERE day=? AND revision=?",
            (state.day, state.revision),
        ).fetchone()
        path = owned_path(
            self.root, f"archives/{state.day}/{state.generation}-r{state.revision:08d}.png"
        )
        receipt = owned_path(self.root, path.with_suffix(".json").relative_to(self.root).as_posix())
        payload = (
            json.loads(existing[0])
            if existing
            else (json.loads(receipt.read_text()) if receipt.is_file() else None)
        )
        expected_ids = (
            [r[0] for r in inputs["ready"]]
            if self.portrait_policy == "approved_only"
            else list(state.dog_ids)
        )
        expected_pending = inputs["pending"] if self.portrait_policy == "approved_only" else []
        mismatch = payload is not None and (
            payload["dog_ids"] != expected_ids
            or payload["portrait_hashes"] != [r[3] for r in inputs["ready"]]
            or payload.get("pending_dog_ids", []) != expected_pending
            or payload.get("portrait_policy", "all_accepted") != self.portrait_policy
        )
        must_advance = (
            (previous is not None and state.revision <= previous["revision"])
            or mismatch
            or (path.exists() and payload is None)
            or (previous is not None and payload is not None)
        )
        # A new membership revision can bind new inputs without a second bump.
        # Existing bytes or a policy/approval change on a bound revision cannot.
        if must_advance:
            db.execute(
                "UPDATE days SET desired_revision=desired_revision+1 WHERE day=?", (state.day,)
            )
            state = self._state(state.day, db)
            self._queue(state, db)
            self.store.audit(
                "collage_inputs_changed",
                {
                    "day": state.day,
                    "generation": state.generation,
                    "revision": state.revision,
                    "policy": self.portrait_policy,
                    "ready": expected_ids,
                    "pending": expected_pending,
                },
                self.clock.now().timestamp(),
                db=db,
            )
        db.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps({"signature": signature, "revision": state.revision}, sort_keys=True)),
        )
        return state

    def _rollover_locked(self):
        today = self._today()
        with self.store.transaction() as db:
            row = self._ensure_day(today, db)
            previous = db.execute("SELECT value FROM meta WHERE key='current_day'").fetchone()
            if previous is None or previous[0] != today:
                db.execute(
                    "INSERT INTO meta(key,value) VALUES('current_day',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (today,),
                )
                db.execute(
                    "UPDATE outbox SET state='obsolete' WHERE state IN ('pending','publishing','reset_pending') AND day != ?",
                    (today,),
                )
                self.store.audit(
                    "daily_rollover",
                    {
                        "from": previous[0] if previous else None,
                        "day": today,
                        "generation": row["generation"],
                    },
                    utc(self.clock.now()).timestamp(),
                    db=db,
                )
                self._queue(self._state(today, db), db)
            state = self._normalize_locked(today, db)
        self._ensure_reset_locked(state)
        return state

    @staticmethod
    def _has_verified_publication(state, db):
        # Current publishers commit receipt + published state atomically. The
        # receipt query also covers legacy catalogs with missing outbox rows.
        return (
            db.execute(
                "SELECT 1 FROM outbox WHERE day=? AND generation=? AND state='published' LIMIT 1",
                (state.day, state.generation),
            ).fetchone()
            is not None
            or db.execute(
                "SELECT 1 FROM publications WHERE json_extract(payload,'$.generation')=? "
                "AND json_extract(payload,'$.state')='verified' LIMIT 1",
                (state.generation,),
            ).fetchone()
            is not None
        )

    @staticmethod
    def _has_verified_full_publication(state, db):
        return (
            db.execute(
                "SELECT 1 FROM outbox WHERE day=? AND generation=? AND revision>0 AND state='published' LIMIT 1",
                (state.day, state.generation),
            ).fetchone()
            is not None
            or db.execute(
                "SELECT 1 FROM publications WHERE json_extract(payload,'$.generation')=? "
                "AND json_extract(payload,'$.revision')>0 AND json_extract(payload,'$.state')='verified' LIMIT 1",
                (state.generation,),
            ).fetchone()
            is not None
        )

    def _ensure_reset_locked(self, state):
        """Keep blank zero publishable until this generation is first verified.

        This blank is an independent reset snapshot. It neither clears nor
        omits accepted membership in the desired composed revision. Archives are
        immutable, and an already published generation is never blanked again.
        """
        with self.store.transaction() as db:
            if self._has_verified_publication(state, db):
                db.execute(
                    "UPDATE outbox SET state='obsolete' WHERE day=? AND generation=? AND state='reset_pending'",
                    (state.day, state.generation),
                )
                return
            existing = db.execute(
                "SELECT payload FROM collages WHERE day=? AND revision=0", (state.day,)
            ).fetchone()
        blank = DayState(state.day, state.generation, 0, ())
        revision = self._archive_image(blank, {}, (), existing)
        with self.store.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO collages VALUES(?,?,?,?,?,?)",
                (
                    state.day,
                    0,
                    state.generation,
                    json.dumps(revision_payload(revision), sort_keys=True),
                    str(revision.output_path),
                    revision.sha256,
                ),
            )
            if state.day != self._today() or self._has_verified_publication(state, db):
                return
            db.execute(
                "INSERT INTO outbox(day,revision,generation,sha256,state) VALUES(?,0,?,?,'reset_pending') "
                "ON CONFLICT(day,revision) DO UPDATE SET state='reset_pending' "
                "WHERE outbox.generation=excluded.generation AND outbox.sha256=excluded.sha256 "
                "AND outbox.state NOT IN ('published','reset_pending')",
                (state.day, state.generation, revision.sha256),
            )

    def reconcile(self) -> DayState:
        """Reconcile the calendar/reset even while composition awaits portraits.

        Returned state retains every accepted member. A missing desired collage
        signals composition_pending to callers; build() still raises that wait.
        """
        with application_lock(self.lock_path):
            state = self._rollover_locked()
            try:
                self._render_locked(state.day)
            except PortraitPendingError:
                with self.store.transaction() as db:
                    changed = db.execute(
                        "INSERT OR IGNORE INTO meta(key,value) VALUES(?,?)",
                        (
                            f"composition_pending:{state.generation}:{state.revision}",
                            "PortraitPendingError",
                        ),
                    ).rowcount
                    if changed:
                        self.store.audit(
                            "composition_pending",
                            {
                                "day": state.day,
                                "generation": state.generation,
                                "revision": state.revision,
                                "error_code": "PortraitPendingError",
                            },
                            self.clock.now().timestamp(),
                            db=db,
                        )
            return state

    def state(self, day=None) -> DayState:
        """Read a snapshot; call reconcile on startup before using this method."""
        with application_lock(self.lock_path):
            with self.store.transaction() as db:
                return self._normalize_locked(self._validate_day(day or self._today()), db)

    def record_sighting(self, dog_id: str, observed_at) -> tuple[DayState, ...]:
        """Add accepted identity by aware event timestamps, never processing time.

        Pass one datetime or all qualifying observation timestamps. A track seen
        on both sides of midnight joins both dates; if only start time exists,
        pass that timestamp only. Repeats update first/last seen without revision.
        """
        timestamps = [observed_at] if isinstance(observed_at, datetime) else list(observed_at)
        if not timestamps:
            raise ValueError("at least one observation timestamp required")
        observed = sorted((self._day(t), utc(t).timestamp()) for t in timestamps)
        if any(day > self._today() for day, _ in observed):
            raise ValueError("future-date observation rejected")
        with application_lock(self.lock_path):
            current = self._rollover_locked()
            if current.revision == 0:
                self._render_locked(current.day)
            with self.store.transaction() as db:
                canonical = self.store.canonical(dog_id, db=db)
                if (
                    db.execute("SELECT state FROM dogs WHERE dog_id=?", (canonical,)).fetchone()[0]
                    != "accepted"
                ):
                    raise ValueError("only accepted canonical identities join daily membership")
                changed = set()
                for day, timestamp in observed:
                    self._ensure_day(day, db)
                    self._normalize_locked(day, db)
                    exists = db.execute(
                        "SELECT 1 FROM membership WHERE day=? AND dog_id=?", (day, canonical)
                    ).fetchone()
                    db.execute(
                        "INSERT INTO membership VALUES(?,?,?,?) ON CONFLICT(day,dog_id) DO UPDATE SET first_seen=min(first_seen,excluded.first_seen),last_seen=max(last_seen,excluded.last_seen)",
                        (day, canonical, timestamp, timestamp),
                    )
                    if not exists:
                        changed.add(day)
                for day in sorted(changed):
                    db.execute(
                        "UPDATE days SET desired_revision=desired_revision+1 WHERE day=?", (day,)
                    )
                    self._queue(self._state(day, db), db)
                states = tuple(self._state(day, db) for day in sorted({d for d, _ in observed}))
            # Persist a newly established current blank even for delayed old-day
            # observations, so startup cannot leave yesterday as desired output.
            if current.day not in {s.day for s in states}:
                self._render_locked(current.day)
            return states

    def _portrait_inputs(self, state, db):
        result, hashes, pending = {}, [], []
        for dog_id in state.dog_ids:
            row = db.execute(
                "SELECT path,sha256 FROM portraits WHERE dog_id=? AND state='validated' ORDER BY rowid LIMIT 1",
                (dog_id,),
            ).fetchone()
            if row is None and self.portrait_policy == "approved_only":
                pending.append(dog_id)
                continue
            if row is None or not row["path"] or not row["sha256"]:
                raise PortraitPendingError(
                    f"validated portrait pending for accepted identity {dog_id}; all membership retained"
                )
            path = Path(row["path"])
            try:
                relative = path.relative_to(self.root)
            except ValueError:
                raise PortraitPendingError(
                    "validated portrait must live inside application data root"
                ) from None
            path = owned_path(self.root, relative.as_posix())
            if not path.is_file() or sha256(path) != row["sha256"]:
                raise PortraitPendingError(
                    "validated portrait missing or hash differs; prior output retained"
                )
            result[dog_id] = path
            hashes.append(row["sha256"])
        return result, tuple(hashes), tuple(pending)

    def _render_locked(self, day):
        with self.store.transaction() as db:
            state = self._normalize_locked(day, db)
            portraits, expected_hashes, pending = self._portrait_inputs(state, db)
            existing = db.execute(
                "SELECT payload FROM collages WHERE day=? AND revision=?", (day, state.revision)
            ).fetchone()
        rendered_state = replace(state, dog_ids=tuple(portraits))
        policy = (
            "all_accepted" if state.revision == 0 and not state.dog_ids else self.portrait_policy
        )
        revision = self._archive_image(
            rendered_state, portraits, expected_hashes, existing, pending, policy
        )
        output = revision.output_path
        with self.store.transaction() as db:
            # Identity corrections can occur independently of the publish lock.
            latest = self._normalize_locked(day, db)
            if latest != state:
                raise StalePublication(
                    "membership changed during local composition; rebuild desired revision"
                )
            db.execute(
                "INSERT OR IGNORE INTO collages VALUES(?,?,?,?,?,?)",
                (
                    day,
                    revision.revision,
                    revision.generation,
                    json.dumps(revision_payload(revision), sort_keys=True),
                    str(output),
                    revision.sha256,
                ),
            )
            if day == self._today():
                db.execute(
                    "UPDATE outbox SET state='obsolete' WHERE state IN ('pending','publishing') AND (day != ? OR generation != ? OR revision != ?)",
                    (day, state.generation, state.revision),
                )
                db.execute(
                    "INSERT OR IGNORE INTO outbox(day,revision,generation,sha256) VALUES(?,?,?,?)",
                    (day, state.revision, state.generation, revision.sha256),
                )
        return revision

    def _archive_image(
        self,
        state,
        portraits,
        expected_hashes,
        existing,
        pending=(),
        portrait_policy="all_accepted",
    ):
        """Create/recover immutable image bytes without changing membership."""
        output = owned_path(
            self.root,
            f"archives/{state.day}/{state.generation}-r{state.revision:08d}.png",
            create_parent=True,
        )
        seed = int.from_bytes(
            hashlib.sha256(f"{state.day}:{state.generation}:{state.revision}".encode()).digest()[
                :8
            ],
            "big",
        )
        if output.exists() and not output.with_suffix(".json").exists():
            # A crash may occur after the complete PNG was linked but before its
            # receipt. Reconstruct deterministically, verify bytes, preserve PNG.
            staging = owned_path(
                self.root, f"staging/recovery-{uuid.uuid4().hex}.png", create_parent=True
            )
            try:
                recovered = self.renderer.render(
                    portraits,
                    day=state.day,
                    generation=state.generation,
                    revision=state.revision,
                    seed=seed,
                    output_path=staging,
                    created_at=self.clock.now(),
                    pending_dog_ids=pending,
                    portrait_policy=portrait_policy,
                )
                if sha256(output) != recovered.sha256:
                    raise ImmutableArchiveError(
                        "incomplete archive differs from deterministic recovery"
                    )
                write_receipt(replace(recovered, output_path=output))
                self.store.audit(
                    "archive_receipt_recovered",
                    {"day": state.day, "revision": state.revision},
                    utc(self.clock.now()).timestamp(),
                )
            finally:
                staging.unlink(missing_ok=True)
                staging.with_suffix(".json").unlink(missing_ok=True)
        if existing or output.exists():
            revision = load_revision(output)
            if (
                revision.dog_ids != state.dog_ids
                or revision.portrait_hashes != expected_hashes
                or revision.generation != state.generation
                or revision.revision != state.revision
                or revision.pending_dog_ids != pending
                or revision.portrait_policy != portrait_policy
            ):
                raise ImmutableArchiveError(
                    "archived inputs changed; require a new audited revision"
                )
        else:
            disk_guard(self.root, int(self.settings.get("MIN_FREE_DISK_MB", 512)))
            revision = self.renderer.render(
                portraits,
                day=state.day,
                generation=state.generation,
                revision=state.revision,
                seed=seed,
                output_path=output,
                created_at=self.clock.now(),
                pending_dog_ids=pending,
                portrait_policy=portrait_policy,
            )
        return revision

    def build(self, day=None) -> CollageRevision:
        """Archive a desired revision; old-day completions never enter outbox."""
        with application_lock(self.lock_path):
            current = self._rollover_locked()
            selected = self._validate_day(day or current.day)
            if selected > current.day:
                raise ValueError("cannot render a future day")
            if selected != current.day:
                self._render_locked(current.day)
            result = self._render_locked(selected)
            if self._today() != current.day:
                changed = self._rollover_locked()
                self._render_locked(changed.day)
            return result

    def rebuild_current_membership(self):
        """Reconcile reviewed assignments/splits from immutable observation times.

        Historical collage bytes are never rewritten. Only the current day set is
        reconstructed; a new desired revision invalidates any earlier publisher.
        """
        with application_lock(self.lock_path):
            current = self._rollover_locked()
            members = {}
            rows = self.store.db.execute(
                "SELECT dog_id,observed_at,payload FROM observations WHERE state='accepted' AND dog_id IS NOT NULL"
            ).fetchall()
            for row in rows:
                dog = self.store.canonical(row["dog_id"])
                payload = json.loads(row["payload"])
                timestamps = [
                    datetime.fromisoformat(c["observed_at"]) for c in payload.get("crops", [])
                ] or [datetime.fromtimestamp(row["observed_at"], ZoneInfo("UTC"))]
                for stamp in timestamps:
                    if self._day(stamp) != current.day:
                        continue
                    value = stamp.timestamp()
                    previous = members.get(dog)
                    members[dog] = (
                        (min(value, previous[0]), max(value, previous[1]))
                        if previous
                        else (value, value)
                    )
            with self.store.transaction() as db:
                old = self._state(current.day, db)
                db.execute("DELETE FROM membership WHERE day=?", (current.day,))
                db.executemany(
                    "INSERT INTO membership VALUES(?,?,?,?)",
                    [(current.day, dog, *times) for dog, times in members.items()],
                )
                if tuple(sorted(members)) != old.dog_ids:
                    db.execute(
                        "UPDATE days SET desired_revision=desired_revision+1 WHERE day=?",
                        (current.day,),
                    )
                    self._queue(self._state(current.day, db), db)
                self.store.audit(
                    "review_membership_rebuilt",
                    {"day": current.day, "members": sorted(members)},
                    self.clock.now().timestamp(),
                    db,
                )
                return self._state(current.day, db)

    def latest(self) -> CollageRevision | None:
        """Return the unverified reset first, then the desired composed revision."""
        with application_lock(self.lock_path):
            state = self._rollover_locked()
            row = self.store.db.execute(
                "SELECT c.path FROM collages c JOIN outbox o USING(day,revision) "
                "WHERE c.day=? AND c.generation=? AND o.generation=? "
                "AND c.revision=0 AND o.state='reset_pending'",
                (state.day, state.generation, state.generation),
            ).fetchone()
            if row is None:
                row = self.store.db.execute(
                    "SELECT path FROM collages WHERE day=? AND revision=?",
                    (state.day, state.revision),
                ).fetchone()
            return load_revision(Path(row[0])) if row else None

    @contextmanager
    def publication_guard(self, revision: CollageRevision):
        """Hold one serialization barrier across bounded upload/replace/readback.

        Usage: with daily.publication_guard(revision) as guard: upload_temp();
        guard.revalidate(); replace_owned_file(); verify_readback(). Revalidate
        again before receipt recording if network work may cross midnight.
        Never put an AI call or unbounded retry inside this context.
        """
        with application_lock(self.lock_path):
            guard = PublicationGuard(self, revision)
            try:
                guard.revalidate()
                yield guard
            finally:
                guard.active = False


__all__ = [
    "DailyManager",
    "DayState",
    "PublicationGuard",
    "StalePublication",
    "PortraitPendingError",
    "PublicationBusyError",
    "application_lock",
]
