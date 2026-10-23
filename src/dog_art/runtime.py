"""Native orchestrator; durable jobs and stage-specific failures, no build settings."""

import json
import logging
import signal
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .budget import BudgetError, Ledger
from .clock import Clock
from .daily import DailyManager, PortraitPendingError
from .description import OllamaDescriber
from .frigate import EventIngestor, FrigateClient, PollReconciler, parse_event
from .identity import IdentityEngine, OnnxImageEncoder
from .portraits import STYLE_VERSION, PortraitService
from .publishing import Publisher
from .safety import disk_guard, fingerprint, owned_path, sha256
from .serialization import description_from_dict, observation_dict, observation_from_dict
from .storage import Store
from .vision import CropExtractor, DecodedFrame, MediaError, decode_image, snapshot_sample

log = logging.getLogger("dog_art")


class DependencyWait(ValueError):
    pass


class PortraitBudgetWait(DependencyWait):
    """No request was reserved; next-day capacity can safely wake this preflight."""


class Pipeline:
    def __init__(
        self,
        settings,
        *,
        mode="shadow",
        clock=None,
        store=None,
        source=None,
        describer=None,
        encoder=None,
        publisher=None,
        portrait_reviewer=None,
    ):
        if mode not in ("shadow", "live"):
            raise ValueError("explicit shadow/live mode required")
        self.settings = settings
        self.mode = mode
        self.clock = clock or Clock()
        self.root = Path(settings["APP_DATA_ROOT"])
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.store = store or Store(owned_path(self.root, "catalog.sqlite"))
        self.source = source
        self.describer = describer
        self.encoder = encoder
        self.publisher = publisher
        self.portrait_reviewer = portrait_reviewer
        self.daily = DailyManager(self.store, settings, self.clock)
        self.identity = IdentityEngine(self.store, settings, self.clock)
        self.stop = False

    def close(self):
        for adapter in (self.source, self.describer, self.portrait_reviewer):
            if adapter and hasattr(adapter, "close"):
                adapter.close()
        self.store.close()

    def _source(self):
        if self.source is None:
            self.source = FrigateClient(self.settings)
        return self.source

    def _describe(self):
        if self.describer is None:
            self.describer = OllamaDescriber(self.settings)
        return self.describer

    def _encoder(self):
        if self.encoder is None:
            if not self.settings.get("LOCAL_IMAGE_ENCODER"):
                raise DependencyWait("image_encoder_unconfigured")
            self.encoder = OnnxImageEncoder(self.settings["LOCAL_IMAGE_ENCODER"])
        return self.encoder

    def _observation(self, oid):
        row = self.store.db.execute(
            "SELECT payload FROM observations WHERE observation_id=?", (oid,)
        ).fetchone()
        if row is None:
            raise ValueError("observation missing")
        return observation_from_dict(json.loads(row[0]))

    def _persist_observations(self, observations):
        with self.store.transaction() as db:
            for o in observations:
                payload = json.dumps(observation_dict(o), sort_keys=True)
                old = db.execute(
                    "SELECT payload FROM observations WHERE observation_id=?", (o.observation_id,)
                ).fetchone()
                if old and old[0] != payload:
                    raise ValueError("immutable observation differs")
                db.execute(
                    "INSERT OR IGNORE INTO observations(observation_id,event_id,track_id,camera,observed_at,payload) VALUES(?,?,?,?,?,?)",
                    (
                        o.observation_id,
                        o.event_id,
                        o.track_id,
                        o.camera,
                        o.observed_at.timestamp(),
                        payload,
                    ),
                )
                self.store.enqueue(
                    "describe",
                    "describe:" + o.observation_id,
                    {"observation_id": o.observation_id},
                    self.clock.now().timestamp(),
                    max_attempts=self.settings["READ_RETRY_ATTEMPTS"],
                    db=db,
                )

    def extract(self, event_id):
        row = self.store.db.execute(
            "SELECT payload FROM events WHERE event_id=?", (event_id,)
        ).fetchone()
        if row is None:
            raise ValueError("event missing")
        event = parse_event(json.loads(row[0]), self.settings["FRIGATE_CAMERA_IDS"])
        if event is None:
            raise ValueError("event no longer qualifies")
        disk_guard(self.root, self.settings["MIN_FREE_DISK_MB"])
        if not event.has_snapshot:
            raise MediaError("snapshot_unavailable")
        from .vision.detector import YoloXDetector

        clean = decode_image(self._source().snapshot(event))
        original = snapshot_sample(event, clean)
        frames = []
        samples = []
        native_errors = []
        detector_path = self.settings.get("LOCAL_DOG_DETECTOR")
        detector = (
            YoloXDetector(detector_path)
            if detector_path and Path(detector_path).is_file()
            else None
        )
        x, y, w, h = event.metadata["data"]["box"]
        anchors = [(original.observed_at, (x + w / 2, y + h))]
        if detector:
            path = event.metadata.get("data", {}).get("path_data", [])
            for entry in path:
                if not isinstance(entry, list) or len(entry) != 2:
                    continue
                point, stamp = entry
                try:
                    when = datetime.fromtimestamp(stamp, UTC)
                except (ValueError, TypeError, OverflowError):
                    continue
                if (
                    event.start_time <= when <= event.end_time
                    and isinstance(point, list)
                    and len(point) == 2
                ):
                    anchors.append((when, tuple(point)))
        unique = {when: point for when, point in anchors}
        ordered = sorted(unique)
        # Keep temporal spread while bounding native frame/model memory.
        limit = self.settings["FRAMES_PER_DOG"]
        if len(ordered) > limit:
            ordered = (
                [ordered[round(i * (len(ordered) - 1) / (limit - 1))] for i in range(limit)]
                if limit > 1
                else [original.observed_at]
            )
        ordered = ([original.observed_at] + [t for t in ordered if t != original.observed_at])[
            :limit
        ]
        for when in ordered:
            try:
                image = decode_image(self._source().recording_frame(event, when))
                # Same timestamp does not prove same sensor/FOV (dual-lens cameras).
                # Verify only the source snapshot's timestamp; other PTZ anchors are
                # usable only after that stream relationship is explicitly verified.
                import numpy as np
                from PIL import Image

                if when == original.observed_at:
                    if abs(image.width / image.height - clean.width / clean.height) > 0.005:
                        raise MediaError("native_fov_mismatch")
                    difference = np.abs(
                        np.asarray(image.resize(clean.size, Image.Resampling.BILINEAR), dtype=float)
                        - np.asarray(clean, dtype=float)
                    ).mean()
                    if difference > 30:
                        raise MediaError("native_fov_unverified")
                elif not frames:
                    raise MediaError("native_fov_unverified")
                frame = DecodedFrame(image, when)
                if detector:
                    sample = detector.sample(
                        frame,
                        unique[when],
                        event.event_id,
                        region_edge=min(1280, max(640, 4 * max(w * image.width, h * image.height))),
                    )
                else:
                    if when != original.observed_at:
                        continue
                    # Reuse source box only for its own timestamp and verified FOV.
                    import numpy as np
                    from PIL import Image

                    if abs(image.width / image.height - clean.width / clean.height) > 0.005:
                        raise MediaError("native_fov_mismatch")
                    difference = np.abs(
                        np.asarray(image.resize(clean.size, Image.Resampling.BILINEAR), dtype=float)
                        - np.asarray(clean, dtype=float)
                    ).mean()
                    if difference > 30:
                        raise MediaError("native_fov_unverified")
                    sample = snapshot_sample(event, image)
                frames.append(frame)
                samples.append(sample)
            except Exception as error:
                native_errors.append(getattr(error, "code", type(error).__name__))
        if not frames:
            frames = [DecodedFrame(clean, original.observed_at)]
            samples = [original]
        observations, rejected = CropExtractor(self.settings).extract(
            event, tuple(frames), tuple(samples), owned_path(self.root, "references")
        )
        self.store.audit(
            "crop_selection",
            {
                "event_id": event_id,
                "observations": len(observations),
                "rejected": rejected,
                "native_errors": native_errors,
                "evidence_mode": "native_timestamped_frames_local_detector"
                if detector
                else "timestamp_matched_snapshot; no clip tracking",
            },
            self.clock.now().timestamp(),
        )
        if not observations:
            raise MediaError("no_usable_dog_crop")
        self._persist_observations(observations)
        return observations

    def describe(self, oid):
        observation = self._observation(oid)
        prior = self.store.db.execute(
            "SELECT payload,model,digest FROM descriptions WHERE observation_id=?", (oid,)
        ).fetchone()
        if prior:
            description = description_from_dict(json.loads(prior[0]))
            description_model, description_digest = prior[1], prior[2]
        else:
            description = self._describe().describe(observation)
            description_model = self.settings["OLLAMA_MODEL"]
            description_digest = self.settings["OLLAMA_MODEL_DIGEST"]
            # Persist successful local inference independently from encoder readiness.
            self.store.db.execute(
                "INSERT OR IGNORE INTO descriptions VALUES(?,?,?,?)",
                (
                    oid,
                    description_model,
                    description_digest,
                    json.dumps(asdict(description), sort_keys=True, separators=(",", ":")),
                ),
            )
        visibility_path = self.settings.get("VISIBILITY_CALIBRATION_PATH")
        if visibility_path:
            from .description.quality import (
                LocalVisibilityAssessor,
                VisibilityPolicy,
                qualify_observation,
            )

            policy = VisibilityPolicy.load(visibility_path)
            assessor = LocalVisibilityAssessor(self.settings)
            try:
                assessments = assessor.assess_views(observation)
            finally:
                assessor.close()
            observation, receipt = qualify_observation(observation, assessments, policy)
            self.store.audit("visibility_qualified", receipt, self.clock.now().timestamp())
        features = self._encoder().encode_views(observation)
        # Unknown full-body evidence stays operator review even with a calibration file.
        decision = self.identity.process(
            observation,
            description,
            features,
            description_model=description_model,
            description_digest=description_digest,
        )
        if decision.dog_id:
            states = self.daily.record_sighting(
                decision.dog_id, [c.observed_at for c in observation.crops]
            )
            for state in states:
                self.store.enqueue(
                    "collage",
                    f"collage:{state.generation}:{state.revision}",
                    {"day": state.day},
                    self.clock.now().timestamp(),
                )
            if self.mode == "live" and self.settings.get("OPENAI_GENERATION_ENABLED"):
                self.store.enqueue(
                    "portrait",
                    "portrait:" + decision.dog_id,
                    {"dog_id": decision.dog_id, "observation_id": oid},
                    self.clock.now().timestamp(),
                    max_attempts=1,
                )
        return decision

    def rebuild_identities(self):
        self.daily.rebuild_current_membership()
        self.daily.build()

    def dispatch(self, job):
        payload = json.loads(job["payload"])
        kind = job["kind"]
        if kind == "extract":
            return self.extract(payload["event_id"])
        if kind == "describe":
            return self.describe(payload["observation_id"])
        if kind == "collage":
            return self.daily.build(payload["day"])
        if kind == "identity_rebuild":
            return self.rebuild_identities()
        if kind == "portrait":
            if self.mode != "live":
                raise DependencyWait("portrait_disabled_in_shadow")
            row = self.store.db.execute(
                "SELECT payload FROM descriptions WHERE observation_id=?",
                (payload["observation_id"],),
            ).fetchone()
            if row is None:
                raise DependencyWait("description_pending")
            try:
                result = PortraitService(self.store, self.settings, self.clock).generate(
                    payload["dog_id"],
                    description_from_dict(json.loads(row[0])),
                    reserve_usd=self.settings.get(
                        "OPENAI_PORTRAIT_RESERVATION_USD", self.settings["OPENAI_DAILY_BUDGET_USD"]
                    ),
                )
            except BudgetError:
                key = self.store.canonical(payload["dog_id"]) + ":" + STYLE_VERSION
                if self.store.db.execute(
                    "SELECT 1 FROM requests WHERE recipe_key=?", (key,)
                ).fetchone():
                    raise
                raise PortraitBudgetWait(
                    "capacity unavailable before request reservation"
                ) from None
            self._queue_portrait_reviews()
            return result
        if kind == "portrait_review":
            return self.review_portrait(payload)
        raise DependencyWait("unsupported_job_kind")

    def _queue_missing_portraits(self):
        if self.mode != "live" or not self.settings.get("OPENAI_GENERATION_ENABLED"):
            return
        rows = self.store.db.execute(
            "SELECT dog_id FROM membership WHERE day=?", (self.clock.day(),)
        ).fetchall()
        for member in rows:
            dog_id = self.store.canonical(member[0])
            key = dog_id + ":" + STYLE_VERSION
            if (
                self.store.db.execute(
                    "SELECT 1 FROM portraits WHERE recipe_key=?", (key,)
                ).fetchone()
                or self.store.db.execute(
                    "SELECT 1 FROM jobs WHERE dedup_key=?", ("portrait:" + dog_id,)
                ).fetchone()
            ):
                continue
            source = next(
                (
                    o[0]
                    for o in self.store.db.execute(
                        "SELECT observation_id,dog_id FROM observations WHERE state='accepted' ORDER BY observed_at,observation_id"
                    ).fetchall()
                    if self.store.canonical(o[1]) == dog_id
                ),
                None,
            )
            if source:
                self.store.enqueue(
                    "portrait",
                    "portrait:" + dog_id,
                    {"dog_id": dog_id, "observation_id": source},
                    self.clock.now().timestamp(),
                    max_attempts=1,
                )

    def _review_key(self, row, observation_id, description_payload):
        from .portraits.review import QA_POLICY_VERSION, QA_PROMPT_SHA256

        return fingerprint(
            {
                "recipe_key": row["recipe_key"],
                "sha256": row["sha256"],
                "observation_id": observation_id,
                "description": json.loads(description_payload),
                "policy": QA_POLICY_VERSION,
                "prompt": QA_PROMPT_SHA256,
                "model": self.settings["OLLAMA_MODEL"],
                "digest": self.settings["OLLAMA_MODEL_DIGEST"],
                "source_policy": self.settings.get("SOURCE_REFERENCE_POLICY", "full_body"),
            }
        )

    def _queue_portrait_reviews(self):
        if (
            self.mode != "live"
            or self.settings.get("PORTRAIT_REVIEW_MODE", "operator") != "local_vlm"
        ):
            return
        for row in self.store.db.execute(
            "SELECT * FROM portraits WHERE state='needs_review' AND path IS NOT NULL AND sha256 IS NOT NULL AND error_code IS NULL"
        ).fetchall():
            source = self.store.db.execute(
                "SELECT o.observation_id,d.payload FROM observations o JOIN descriptions d USING(observation_id) WHERE o.dog_id=? AND o.state='accepted' ORDER BY o.observed_at,o.observation_id LIMIT 1",
                (row["dog_id"],),
            ).fetchone()
            if source:
                key = self._review_key(row, source[0], source[1])
                self.store.enqueue(
                    "portrait_review",
                    "portrait_review:" + key,
                    {
                        "recipe_key": row["recipe_key"],
                        "observation_id": source[0],
                        "review_key": key,
                    },
                    self.clock.now().timestamp(),
                    max_attempts=self.settings["READ_RETRY_ATTEMPTS"],
                )

    def review_portrait(self, payload):
        if (
            self.mode != "live"
            or self.settings.get("PORTRAIT_REVIEW_MODE", "operator") != "local_vlm"
        ):
            raise DependencyWait("local portrait review disabled")
        row = self.store.db.execute(
            "SELECT * FROM portraits WHERE recipe_key=?", (payload["recipe_key"],)
        ).fetchone()
        if not row or not row["path"] or not row["sha256"]:
            raise DependencyWait("saved portrait required")
        if row["state"] == "validated":
            return {"decision": "already_validated"}
        if row["state"] != "needs_review":
            raise DependencyWait("saved portrait not ready for review")
        if row["error_code"]:
            raise DependencyWait("saved portrait recovery requires operator review")
        source = self.store.db.execute(
            "SELECT o.dog_id,d.payload,d.model,d.digest FROM observations o JOIN descriptions d USING(observation_id) WHERE o.observation_id=? AND o.state='accepted'",
            (payload["observation_id"],),
        ).fetchone()
        if not source or self.store.canonical(source[0]) != self.store.canonical(row["dog_id"]):
            raise ValueError("portrait source association differs")
        if payload["review_key"] != self._review_key(row, payload["observation_id"], source[1]):
            return {"decision": "stale_policy; current review queued separately"}
        expected_review = {
            "observation_id": payload["observation_id"],
            "source": dict(source),
            "portrait": {k: row[k] for k in ("dog_id", "recipe", "path", "sha256", "state")},
            "canonical": self.store.canonical(row["dog_id"]),
        }
        portrait_root = Path(self.settings["APP_DATA_ROOT"]) / "portraits"
        relative = Path(row["path"]).relative_to(portrait_root)
        portrait_path = owned_path(portrait_root, relative.as_posix())
        if sha256(portrait_path) != row["sha256"]:
            raise ValueError("portrait changed before review")
        if self.portrait_reviewer is None:
            from .portraits.review import LocalPortraitReviewer

            self.portrait_reviewer = LocalPortraitReviewer(self.settings)
        report = self.portrait_reviewer.review(
            Path(row["path"]), row["sha256"], description_from_dict(json.loads(source[1]))
        )
        self.store.audit(
            "portrait_local_review",
            {"recipe_key": row["recipe_key"], "review_key": payload["review_key"], **report},
            self.clock.now().timestamp(),
        )
        if report.get("retryable") is True:
            raise RuntimeError("transient local portrait review failure")
        if report["decision"] == "pass":
            from importlib.resources import files

            from .portraits.review import QA_POLICY_VERSION, QA_PROMPT_SHA256

            expected = {
                "image_sha256": row["sha256"],
                "description_sha256": fingerprint(
                    asdict(description_from_dict(json.loads(source[1])))
                ),
                "style_sha256": sha256(
                    Path(str(files("dog_art").joinpath("resources/dog-watercolor-transparent.png")))
                ),
                "model": self.settings["OLLAMA_MODEL"],
                "digest": self.settings["OLLAMA_MODEL_DIGEST"],
                "policy_version": QA_POLICY_VERSION,
                "prompt_sha256": QA_PROMPT_SHA256,
                "source_reference_policy": self.settings.get(
                    "SOURCE_REFERENCE_POLICY", "full_body"
                ),
            }
            evidence = report.get("evidence", {})
            checks = evidence.get("checks", {})
            if (
                any(report.get(k) != v for k, v in expected.items())
                or evidence.get("input_provenance") != "generated_artwork"
                or evidence.get("model_verified_before_and_after") is not True
                or evidence.get("reasons") != []
                or set(checks)
                != {
                    "one_dog",
                    "complete_anatomy",
                    "no_extras",
                    "style_matches",
                    "confirmed_facts_match",
                    "clean_exterior",
                }
                or not all(v is True for v in checks.values())
            ):
                raise ValueError("passing portrait review provenance differs")
            from .portraits import StalePortraitReview

            if payload["review_key"] != self._review_key(row, payload["observation_id"], source[1]):
                return {"decision": "stale_policy; current review queued separately"}
            try:
                PortraitService(self.store, self.settings, self.clock).accept(
                    row["recipe_key"],
                    reviewer="pinned local Ollama saved-output QA",
                    evidence=json.dumps(
                        {"review_key": payload["review_key"], **report}, sort_keys=True
                    ),
                    expected_review=expected_review,
                )
            except StalePortraitReview:
                self.store.audit(
                    "portrait_review_stale",
                    {"recipe_key": row["recipe_key"]},
                    self.clock.now().timestamp(),
                )
                return {"decision": "stale_source; fresh associated evidence required"}
        return report

    def _resume_portrait_budget(self):
        if self.mode != "live" or not self.settings.get("OPENAI_GENERATION_ENABLED"):
            return
        self.store.db.execute(
            "UPDATE jobs SET state='queued',available_at=?,error_code=NULL WHERE kind='portrait' AND state='dependency_wait' AND error_code='PortraitBudgetWait' AND attempts<max_attempts AND json_extract(payload,'$.budget_wait_day')!=?",
            (self.clock.now().timestamp(), self.clock.day()),
        )

    def work_once(self):
        job = self.store.claim(self.clock.now().timestamp(), self.settings["JOB_LEASE_SECONDS"])
        if job is None:
            return False
        try:
            self.dispatch(job)
            self.store.finish(job["job_id"], job["lease_token"])
        except PortraitBudgetWait:
            # No ledger row exists, so this did not consume a paid attempt.
            self.store.db.execute(
                "UPDATE jobs SET state='dependency_wait',attempts=attempts-1,lease_until=NULL,lease_token=NULL,error_code='PortraitBudgetWait',payload=json_set(payload,'$.budget_wait_day',?) WHERE job_id=? AND lease_token=?",
                (self.clock.day(), job["job_id"], job["lease_token"]),
            )
        except (DependencyWait, PortraitPendingError) as error:
            with self.store.transaction() as db:
                db.execute(
                    "UPDATE jobs SET state='dependency_wait',lease_until=NULL,lease_token=NULL,error_code=? WHERE job_id=? AND lease_token=?",
                    (type(error).__name__, job["job_id"], job["lease_token"]),
                )
        except Exception as error:
            code = getattr(error, "code", type(error).__name__)
            retry_at = self.clock.now().timestamp() + min(
                self.settings["RETRY_MAX_SECONDS"],
                self.settings["RETRY_BASE_SECONDS"] * 2 ** (job["attempts"] - 1),
            )
            # Paid requests never get an automatic duplicate; their ledger blocks retries.
            self.store.finish(
                job["job_id"],
                job["lease_token"],
                error_code=code,
                retry_at=retry_at if job["kind"] != "portrait" else None,
            )
            log.warning(json.dumps({"code": code, "job_id": job["job_id"], "kind": job["kind"]}))
        return True

    def retry_waiting(self):
        # Explicit operator action after resolving a dependency; finite attempts remain.
        with self.store.transaction() as db:
            return db.execute(
                "UPDATE jobs SET state='queued',available_at=?,error_code=NULL WHERE state='dependency_wait' AND attempts<max_attempts",
                (self.clock.now().timestamp(),),
            ).rowcount

    def publish_latest(self):
        if self.mode != "live" or not self.settings.get("PUBLISH_ENABLED"):
            return None
        revision = self.daily.latest()
        if revision is None:
            return None
        row = self.store.db.execute(
            "SELECT state FROM outbox WHERE day=? AND revision=?", (revision.day, revision.revision)
        ).fetchone()
        if row and row[0] == "published":
            return None
        publisher = self.publisher or Publisher(self.store, self.settings, self.clock, self.daily)
        return publisher.publish(revision)

    def tick(self, *, reconcile_source=True, max_jobs=20):
        # Rollover and publication do not wait for an AI/source outage.
        try:
            self.daily.reconcile()
        except Exception as error:
            log.warning(json.dumps({"code": type(error).__name__, "stage": "rollover"}))
        self._resume_portrait_budget()
        self._queue_missing_portraits()
        self._queue_portrait_reviews()
        if reconcile_source:
            try:
                PollReconciler(
                    self._source(), EventIngestor(self.store, self.settings, self.clock)
                ).reconcile()
            except Exception as error:
                log.warning(
                    json.dumps(
                        {"code": getattr(error, "code", type(error).__name__), "stage": "source"}
                    )
                )
        for _ in range(max_jobs):
            if self.stop or not self.work_once():
                break
        try:
            self.publish_latest()
        except Exception as error:
            log.warning(json.dumps({"code": type(error).__name__, "stage": "publish"}))
        return self.store.status()

    def run(self, *, once=False):
        Ledger(self.store).recover()
        PortraitService(self.store, self.settings, self.clock).recover_saved()
        if once:
            return self.tick()

        def stop(signum, frame):
            self.stop = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        next_poll = 0
        while not self.stop:
            now = time.monotonic()
            poll = now >= next_poll
            self.tick(reconcile_source=poll)
            if poll:
                next_poll = time.monotonic() + self.settings["EVENT_POLL_SECONDS"]
            for _ in range(10):
                if self.stop:
                    break
                time.sleep(0.1)
