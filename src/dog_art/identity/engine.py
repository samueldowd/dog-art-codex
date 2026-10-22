"""Serialized compare/enroll and optimistic, reversible reviewed corrections."""

import json
import math
import uuid
from dataclasses import asdict

from dog_art.contracts import DogDescription, IdentityDecision, ImageFeature
from dog_art.description import has_observed_appearance, parse_description, validate_observation

from .matching import Calibration, decide, space


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _view_payload(features):
    return [list(f.values) for f in features]


class IdentityEngine:
    """No network or paid calls. BEGIN IMMEDIATE serializes comparisons and enrollment.

    Observations must already exist in the ingest catalog. Feature vector JSON is
    a list of per-view vectors; dimension is the dimension of each individual view.
    Corrections preserve original crop payloads and historical collage files.
    """

    def __init__(self, store, settings, clock, *, calibration=None):
        self.store, self.settings, self.clock = store, settings, clock
        self.calibration_error = None
        self.calibration = calibration
        if (
            calibration is None
            and settings.get("IDENTITY_CALIBRATION_PATH")
            and settings.get("IDENTITY_MODE", "shadow") != "per_observation"
        ):
            try:
                self.calibration = Calibration.load(settings["IDENTITY_CALIBRATION_PATH"])
                for key, attribute in (
                    ("IDENTITY_MATCH_THRESHOLD", "match_threshold"),
                    ("IDENTITY_NEW_THRESHOLD", "new_threshold"),
                    ("IDENTITY_SCORE_MARGIN", "score_margin"),
                ):
                    if type(settings.get(key)) not in (int, float) or settings[key] != getattr(
                        self.calibration, attribute
                    ):
                        raise ValueError("configured thresholds differ from approved calibration")
            except (ValueError, OSError, TypeError, KeyError):
                self.calibration = None
                self.calibration_error = "configured calibration unavailable or invalid"

    def _galleries(self, db):
        galleries = {
            r["dog_id"]: []
            for r in db.execute(
                "SELECT dog_id FROM dogs WHERE canonical_id IS NULL AND state='accepted'"
            )
        }
        rows = db.execute("""SELECT o.dog_id,f.*,d.payload AS description FROM observations o
            JOIN features f USING(observation_id) JOIN descriptions d USING(observation_id)
            WHERE o.dog_id IS NOT NULL AND o.state='accepted' """)
        for row in rows:
            canonical = self.store.canonical(row["dog_id"], db)
            if canonical not in galleries:
                continue
            values = json.loads(row["vector"])
            # Accept pre-existing single-view rows as well as the explicit multi-view form.
            if values and isinstance(values[0], (float, int)):
                values = [values]
            views = tuple(
                ImageFeature(tuple(v), row["model"], row["digest"], row["preprocessing"])
                for v in values
            )
            galleries[canonical].append((views, parse_description(row["description"])))
        return galleries

    def process(
        self,
        observation,
        description: DogDescription,
        features,
        *,
        description_model=None,
        description_digest=None,
    ):
        """Persist evidence and a decision once; uncertain observations stay review-only."""
        validate_observation(observation)
        features = (features,) if isinstance(features, ImageFeature) else tuple(features)
        if not features or len(features) != len(observation.crops):
            raise ValueError("one real-camera feature per crop required")
        feature_space = space(features[0])
        if any(space(f) != feature_space for f in features):
            raise ValueError("incompatible feature spaces")
        # Strict validation also applies to manually constructed dataclass instances.
        description_payload = json.loads(_json(asdict(description)))
        description = parse_description(description_payload)
        description_model = description_model or self.settings.get("OLLAMA_MODEL", "")
        description_digest = description_digest or self.settings.get("OLLAMA_MODEL_DIGEST", "")
        if not description_model or not description_digest:
            raise ValueError("verified description model provenance required")
        now = self.clock.now().timestamp()
        with self.store.transaction() as db:
            row = db.execute(
                "SELECT * FROM observations WHERE observation_id=?", (observation.observation_id,)
            ).fetchone()
            if row is None or (row["event_id"], row["track_id"], row["camera"]) != (
                observation.event_id,
                observation.track_id,
                observation.camera,
            ):
                raise ValueError("observation must match durable ingest record")
            if abs(row["observed_at"] - observation.observed_at.timestamp()) > 0.001:
                raise ValueError("observation timestamp differs from ingest record")
            if row["dog_id"] is not None and row["state"] == "accepted":
                canonical = self.store.canonical(row["dog_id"], db)
                return IdentityDecision(
                    "known",
                    canonical,
                    model_version=":".join(map(str, feature_space)),
                    rationale=(
                        "durable observation already assigned; replay is not returning-dog recognition",
                    ),
                )
            encoded = _json(_view_payload(features))
            existing = db.execute(
                "SELECT * FROM features WHERE observation_id=?", (observation.observation_id,)
            ).fetchone()
            if existing is not None and (
                existing["model"],
                existing["digest"],
                existing["preprocessing"],
                existing["dimension"],
                existing["vector"],
            ) != (*feature_space, encoded):
                raise ValueError("immutable observation feature evidence differs")
            payload = _json(description_payload)
            previous_description = db.execute(
                "SELECT * FROM descriptions WHERE observation_id=?", (observation.observation_id,)
            ).fetchone()
            if previous_description is not None:
                same_model = (previous_description["model"], previous_description["digest"]) == (
                    description_model,
                    description_digest,
                )
                same_facts = parse_description(previous_description["payload"]) == description
                if not same_model or not same_facts:
                    raise ValueError("immutable description evidence differs")
            db.execute(
                "INSERT OR IGNORE INTO features VALUES(?,?,?,?,?,?)",
                (observation.observation_id, *feature_space, encoded),
            )
            db.execute(
                "INSERT OR IGNORE INTO descriptions VALUES(?,?,?,?)",
                (observation.observation_id, description_model, description_digest, payload),
            )
            mode = self.settings.get("IDENTITY_MODE", "shadow")
            if mode == "per_observation":
                quality_values = (observation.quality, *(c.quality for c in observation.crops))
                valid_quality = all(
                    type(q) in (int, float) and math.isfinite(q) and 0 < q <= 1
                    for q in quality_values
                )
                stable_conflict = any(
                    item.startswith("conflicting views:")
                    and item.removeprefix("conflicting views:").strip()
                    not in {"pose", "accessories"}
                    for item in description.uncertainty
                )
                observed_appearance = has_observed_appearance(description)
                reason = (
                    "invalid or unusable observation quality"
                    if not valid_quality
                    else "conflicting appearance evidence"
                    if stable_conflict
                    else "insufficient observed stable appearance evidence"
                    if not observed_appearance
                    else None
                )
                decision = IdentityDecision(
                    "uncertain" if reason else "new",
                    None,
                    model_version=":".join(map(str, feature_space)),
                    rationale=(
                        "per-observation appearance entry; returning-dog recognition deferred",
                    ),
                    abstention_reason=reason,
                )
            else:
                decision = decide(
                    features,
                    description,
                    self._galleries(db),
                    observation.quality,
                    self.calibration,
                )
            reviewed = db.execute(
                "SELECT payload FROM audit WHERE code='visibility_review' ORDER BY created_at DESC,rowid DESC"
            ).fetchall()
            visibility = next(
                (
                    json.loads(r[0])
                    for r in reviewed
                    if json.loads(r[0]).get("observation_id") == observation.observation_id
                ),
                {},
            )
            manual_full_body = visibility.get("full_body") is True
            manual_rejection = visibility.get("full_body") is False
            if manual_rejection or (
                not all(c.full_body for c in observation.crops) and not manual_full_body
            ):
                decision = IdentityDecision(
                    "uncertain",
                    None,
                    decision.candidates,
                    decision.model_version,
                    decision.calibration_version,
                    decision.rationale,
                    "full-body visibility rejected by operator"
                    if manual_rejection
                    else "full-body visibility not verified",
                )
            if mode not in {"calibrated_auto", "per_observation"} and decision.outcome in {
                "new",
                "known",
            }:
                decision = IdentityDecision(
                    "uncertain",
                    None,
                    decision.candidates,
                    decision.model_version,
                    decision.calibration_version,
                    decision.rationale,
                    "identity mode requires operator review",
                )
            if decision.outcome == "new":
                dog_id = uuid.uuid4().hex
                db.execute("INSERT INTO dogs(dog_id,created_at) VALUES(?,?)", (dog_id, now))
                decision = IdentityDecision(
                    "new",
                    dog_id,
                    decision.candidates,
                    decision.model_version,
                    decision.calibration_version,
                    decision.rationale,
                )
            if decision.dog_id:
                db.execute(
                    "UPDATE observations SET dog_id=?,state='accepted' WHERE observation_id=?",
                    (decision.dog_id, observation.observation_id),
                )
            self.store.audit(
                "identity_decision",
                {"observation_id": observation.observation_id, **asdict(decision)},
                now,
                db,
            )
            return decision

    def review(self):
        """Return pending IDs/quality metadata only; private crops remain on local disk."""
        return [
            dict(r)
            for r in self.store.db.execute(
                "SELECT observation_id,event_id,camera,observed_at FROM observations WHERE state='review' ORDER BY observed_at"
            )
        ]

    def _snapshot(self, db, observations=(), dogs=()):
        return {
            "observations": {
                oid: dict(
                    db.execute(
                        "SELECT observation_id,dog_id,state FROM observations WHERE observation_id=?",
                        (oid,),
                    ).fetchone()
                )
                for oid in observations
            },
            "dogs": {
                did: dict(row)
                if (
                    row := db.execute(
                        "SELECT dog_id,state,canonical_id FROM dogs WHERE dog_id=?", (did,)
                    ).fetchone()
                )
                else None
                for did in dogs
            },
        }

    def _correction(self, db, kind, before, after, reason):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise ValueError("bounded operator correction reason required")
        cid = uuid.uuid4().hex
        now = self.clock.now().timestamp()
        db.execute(
            "INSERT INTO corrections VALUES(?,?,?,?,?,0)",
            (cid, now, kind, _json(before), _json(after)),
        )
        self.store.audit(
            "identity_correction", {"correction_id": cid, "kind": kind, "reason": reason}, now, db
        )
        self.store.enqueue(
            "identity_rebuild", "identity_rebuild:" + cid, {"correction_id": cid}, now, db=db
        )
        return cid

    def assign(self, observation_id, dog_id=None, *, reason):
        """Reviewed enrollment (dog_id=None) or assignment; never auto-regenerates art."""
        with self.store.transaction() as db:
            row = db.execute(
                "SELECT * FROM observations WHERE observation_id=?", (observation_id,)
            ).fetchone()
            if (
                row is None
                or not db.execute(
                    "SELECT 1 FROM features WHERE observation_id=?", (observation_id,)
                ).fetchone()
            ):
                raise ValueError("review requires persisted real-image evidence")
            new = dog_id is None
            dog_id = uuid.uuid4().hex if new else self.store.canonical(dog_id, db)
            before = self._snapshot(db, (observation_id,), (dog_id,))
            if new:
                db.execute(
                    "INSERT INTO dogs(dog_id,created_at) VALUES(?,?)",
                    (dog_id, self.clock.now().timestamp()),
                )
            elif before["dogs"][dog_id]["state"] != "accepted":
                raise ValueError("target identity is not accepted")
            db.execute(
                "UPDATE observations SET dog_id=?,state='accepted' WHERE observation_id=?",
                (dog_id, observation_id),
            )
            after = self._snapshot(db, (observation_id,), (dog_id,))
            return {
                "dog_id": dog_id,
                "correction_id": self._correction(db, "assign", before, after, reason),
            }

    def merge(self, source_id, target_id, *, reason):
        """Alias canonical identities; preserve every original observation and portrait."""
        with self.store.transaction() as db:
            source_id, target_id = (
                self.store.canonical(source_id, db),
                self.store.canonical(target_id, db),
            )
            if source_id == target_id:
                raise ValueError("identities already canonical-equivalent")
            before = self._snapshot(db, dogs=(source_id, target_id))
            if any(d["state"] != "accepted" for d in before["dogs"].values()):
                raise ValueError("merge requires accepted identities")
            db.execute("UPDATE dogs SET canonical_id=? WHERE dog_id=?", (target_id, source_id))
            return self._correction(
                db, "merge", before, self._snapshot(db, dogs=(source_id, target_id)), reason
            )

    def split(self, source_id, observation_ids, *, reason):
        """Move reviewed observations into a new identity, keeping originals/history."""
        observation_ids = tuple(dict.fromkeys(observation_ids))
        if not observation_ids:
            raise ValueError("split observations required")
        with self.store.transaction() as db:
            source_id = self.store.canonical(source_id, db)
            for oid in observation_ids:
                row = db.execute(
                    "SELECT dog_id FROM observations WHERE observation_id=?", (oid,)
                ).fetchone()
                if (
                    row is None
                    or row["dog_id"] is None
                    or self.store.canonical(row["dog_id"], db) != source_id
                ):
                    raise ValueError("split observation does not belong to identity")
            dog_id = uuid.uuid4().hex
            before = self._snapshot(db, observation_ids, (dog_id, source_id))
            db.execute(
                "INSERT INTO dogs(dog_id,created_at) VALUES(?,?)",
                (dog_id, self.clock.now().timestamp()),
            )
            for oid in observation_ids:
                db.execute("UPDATE observations SET dog_id=? WHERE observation_id=?", (dog_id, oid))
            cid = self._correction(
                db,
                "split",
                before,
                self._snapshot(db, observation_ids, (dog_id, source_id)),
                reason,
            )
            return {"dog_id": dog_id, "correction_id": cid}

    def undo(self, correction_id, *, reason):
        """Reverse only untouched affected records; later activity requires fresh review."""
        with self.store.transaction() as db:
            row = db.execute(
                "SELECT * FROM corrections WHERE correction_id=?", (correction_id,)
            ).fetchone()
            if row is None or row["undone"] or row["kind"] == "undo":
                raise ValueError("correction missing or already undone")
            before, after = json.loads(row["before_json"]), json.loads(row["after_json"])
            current = self._snapshot(db, after["observations"], after["dogs"])
            if current != after:
                raise ValueError("later correction conflicts; review before undo")
            new_dogs = [did for did, state in before["dogs"].items() if state is None]
            for did in new_dogs:
                owned = set(after["observations"])
                observed = {
                    r[0]
                    for r in db.execute(
                        "SELECT observation_id FROM observations WHERE dog_id=?", (did,)
                    )
                }
                if (
                    not observed <= owned
                    or db.execute("SELECT 1 FROM portraits WHERE dog_id=?", (did,)).fetchone()
                ):
                    raise ValueError("identity has later evidence or artwork; review before undo")
            for oid, item in before["observations"].items():
                db.execute(
                    "UPDATE observations SET dog_id=?,state=? WHERE observation_id=?",
                    (item["dog_id"], item["state"], oid),
                )
            for did, item in before["dogs"].items():
                if item is None:
                    db.execute(
                        "UPDATE dogs SET state='retired',canonical_id=NULL WHERE dog_id=?", (did,)
                    )
                else:
                    db.execute(
                        "UPDATE dogs SET state=?,canonical_id=? WHERE dog_id=?",
                        (item["state"], item["canonical_id"], did),
                    )
            db.execute("UPDATE corrections SET undone=1 WHERE correction_id=?", (correction_id,))
            self._correction(
                db, "undo", after, self._snapshot(db, after["observations"], after["dogs"]), reason
            )
            return correction_id
