"""Local SQLite catalog; short transactions, immutable evidence and durable work."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY, camera TEXT NOT NULL, start_time REAL NOT NULL, end_time REAL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS observations(observation_id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(event_id), track_id TEXT NOT NULL, camera TEXT NOT NULL, observed_at REAL NOT NULL, payload TEXT NOT NULL, dog_id TEXT, state TEXT NOT NULL DEFAULT 'review', UNIQUE(event_id,track_id));
CREATE TABLE IF NOT EXISTS dogs(dog_id TEXT PRIMARY KEY, created_at REAL NOT NULL, state TEXT NOT NULL DEFAULT 'accepted', canonical_id TEXT REFERENCES dogs(dog_id));
CREATE TABLE IF NOT EXISTS features(observation_id TEXT PRIMARY KEY REFERENCES observations(observation_id), model TEXT NOT NULL, digest TEXT NOT NULL, preprocessing TEXT NOT NULL, dimension INTEGER NOT NULL, vector TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS descriptions(observation_id TEXT PRIMARY KEY REFERENCES observations(observation_id), model TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS corrections(correction_id TEXT PRIMARY KEY, created_at REAL NOT NULL, kind TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL, undone INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS jobs(job_id TEXT PRIMARY KEY, kind TEXT NOT NULL, dedup_key TEXT NOT NULL UNIQUE, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL, available_at REAL NOT NULL, lease_until REAL, lease_token TEXT, error_code TEXT);
CREATE TABLE IF NOT EXISTS portraits(recipe_key TEXT PRIMARY KEY, dog_id TEXT NOT NULL REFERENCES dogs(dog_id), recipe TEXT NOT NULL, state TEXT NOT NULL, path TEXT, sha256 TEXT, request_id TEXT, error_code TEXT);
CREATE TABLE IF NOT EXISTS requests(request_id TEXT PRIMARY KEY, recipe_key TEXT NOT NULL UNIQUE REFERENCES portraits(recipe_key), day TEXT NOT NULL, scope TEXT, reserved_usd REAL NOT NULL CHECK(reserved_usd>0), state TEXT NOT NULL, created_at REAL NOT NULL, remote_id TEXT, usage TEXT);
CREATE TABLE IF NOT EXISTS budget_scopes(scope TEXT PRIMARY KEY, cap_usd REAL NOT NULL CHECK(cap_usd>=0));
CREATE TABLE IF NOT EXISTS days(day TEXT PRIMARY KEY, generation TEXT NOT NULL UNIQUE, desired_revision INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS membership(day TEXT NOT NULL REFERENCES days(day), dog_id TEXT NOT NULL REFERENCES dogs(dog_id), first_seen REAL NOT NULL, last_seen REAL NOT NULL, PRIMARY KEY(day,dog_id));
CREATE TABLE IF NOT EXISTS collages(day TEXT NOT NULL REFERENCES days(day), revision INTEGER NOT NULL, generation TEXT NOT NULL, payload TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, PRIMARY KEY(day,revision));
CREATE TABLE IF NOT EXISTS outbox(day TEXT NOT NULL, revision INTEGER NOT NULL, generation TEXT NOT NULL, sha256 TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', PRIMARY KEY(day,revision));
CREATE TABLE IF NOT EXISTS publications(receipt_id TEXT PRIMARY KEY, created_at REAL NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(audit_id TEXT PRIMARY KEY, created_at REAL NOT NULL, code TEXT NOT NULL, payload TEXT NOT NULL);
"""


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ValueError("database symlink forbidden")
        self.db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            self.db.close()
            raise ValueError("incompatible database schema; restore compatible release/backup")
        if version == 0:
            # An existing nonempty unknown database must never be silently adopted.
            tables = self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if tables:
                raise ValueError("unversioned existing database requires explicit migration")
            self.db.executescript(
                "BEGIN IMMEDIATE;" + SCHEMA + f"PRAGMA user_version={SCHEMA_VERSION};COMMIT;"
            )
        self.db.execute("PRAGMA journal_mode=WAL")
        self.path.chmod(0o600)

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def backup(self, output: Path):
        if output.exists():
            raise ValueError("backup destination exists")
        output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = sqlite3.connect(output)
        try:
            self.db.backup(target)
        finally:
            target.close()
        output.chmod(0o600)
        return output

    def canonical(self, dog_id: str, db=None) -> str:
        db = db or self.db
        visited = set()
        while True:
            if dog_id in visited:
                raise ValueError("identity alias cycle")
            visited.add(dog_id)
            row = db.execute("SELECT canonical_id FROM dogs WHERE dog_id=?", (dog_id,)).fetchone()
            if row is None:
                raise ValueError("unknown identity")
            if row["canonical_id"] is None:
                return dog_id
            dog_id = row["canonical_id"]

    def enqueue(self, kind: str, key: str, payload: dict, now: float, max_attempts=3, db=None):
        if max_attempts < 1:
            raise ValueError("finite positive attempts required")
        conn = db or self.db
        conn.execute(
            "INSERT OR IGNORE INTO jobs(job_id,kind,dedup_key,payload,max_attempts,available_at) VALUES(?,?,?,?,?,?)",
            (uuid.uuid4().hex, kind, key, json.dumps(payload), max_attempts, now),
        )

    def claim(self, now: float, lease_seconds=600, kinds=None):
        if lease_seconds <= 0:
            raise ValueError("positive lease required")
        with self.transaction() as db:
            db.execute(
                "UPDATE jobs SET state='queued',lease_until=NULL,lease_token=NULL WHERE state='running' AND lease_until<=? AND attempts<max_attempts",
                (now,),
            )
            db.execute(
                "UPDATE jobs SET state='exhausted',error_code='lease_expired' WHERE state='running' AND lease_until<=? AND attempts>=max_attempts",
                (now,),
            )
            sql = "SELECT * FROM jobs WHERE state='queued' AND available_at<=? AND attempts<max_attempts"
            args = [now]
            if kinds:
                sql += " AND kind IN (" + ",".join("?" for _ in kinds) + ")"
                args += list(kinds)
            row = db.execute(sql + " ORDER BY available_at,job_id LIMIT 1", args).fetchone()
            if not row:
                return None
            token = uuid.uuid4().hex
            db.execute(
                "UPDATE jobs SET state='running',attempts=attempts+1,lease_until=?,lease_token=? WHERE job_id=?",
                (now + lease_seconds, token, row["job_id"]),
            )
            return dict(
                db.execute("SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)).fetchone()
            )

    def finish(self, job_id, token, *, error_code=None, retry_at=None):
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE job_id=? AND state='running' AND lease_token=?",
                (job_id, token),
            ).fetchone()
            if not row:
                raise ValueError("stale job lease")
            state = (
                "done"
                if error_code is None
                else (
                    "queued"
                    if retry_at is not None and row["attempts"] < row["max_attempts"]
                    else "exhausted"
                )
            )
            db.execute(
                "UPDATE jobs SET state=?,available_at=?,lease_until=NULL,lease_token=NULL,error_code=? WHERE job_id=?",
                (state, retry_at or row["available_at"], error_code, job_id),
            )

    def audit(self, code, payload, now, db=None):
        (db or self.db).execute(
            "INSERT INTO audit VALUES(?,?,?,?)",
            (uuid.uuid4().hex, now, code, json.dumps(payload, sort_keys=True)),
        )

    def status(self):
        return {
            "schema": SCHEMA_VERSION,
            "jobs": {
                r[0]: r[1]
                for r in self.db.execute("SELECT state,count(*) FROM jobs GROUP BY state")
            },
            "identities": self.db.execute(
                "SELECT count(*) FROM dogs WHERE canonical_id IS NULL"
            ).fetchone()[0],
            "review": self.db.execute(
                "SELECT count(*) FROM observations WHERE state='review'"
            ).fetchone()[0],
            "requests": {
                r[0]: r[1]
                for r in self.db.execute("SELECT state,count(*) FROM requests GROUP BY state")
            },
            "current_day": self.db.execute(
                "SELECT value FROM meta WHERE key='current_day'"
            ).fetchone()[0]
            if self.db.execute("SELECT 1 FROM meta WHERE key='current_day'").fetchone()
            else None,
        }
