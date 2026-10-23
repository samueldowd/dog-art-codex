"""Explicit operator CLI. Offline and shadow paths never spend or publish."""

import argparse
import json
import logging
import os
import shutil
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

from . import __version__
from .clock import Clock
from .diagnostics import doctor
from .safety import owned_path
from .settings import ConfigError, Settings, load_settings
from .storage import Store


def parser():
    p = argparse.ArgumentParser(prog="dog-art")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--config", type=Path, default=Path("config/app.toml"))
    p.add_argument("--secrets-file", type=Path, default=Path("config/.env"))
    p.add_argument(
        "--data-root",
        type=Path,
        help="explicit application data root override; never sourced from dotenv",
    )
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("doctor")
    d.add_argument("--mode", choices=("offline", "live"), default="offline")
    d.add_argument("--redact", action="store_true")
    d = sub.add_parser("status")
    d.add_argument("--redact", action="store_true")
    d = sub.add_parser("run")
    d.add_argument("--mode", choices=("shadow", "live"), required=True)
    d.add_argument("--once", action="store_true")
    d = sub.add_parser("rollover")
    d.add_argument(
        "--publish",
        action="store_true",
        help="publish current date only if enabled by app settings",
    )
    d = sub.add_parser("backup")
    d.add_argument("--output", type=Path, required=True)
    d = sub.add_parser("retry")
    d.add_argument("--dependencies", action="store_true", required=True)
    d = sub.add_parser("replay")
    d.add_argument("--manifest", type=Path, required=True)
    d.add_argument("--sandbox", type=Path, required=True)
    d = sub.add_parser("collage")
    s = d.add_subparsers(dest="action", required=True)
    r = s.add_parser("render")
    r.add_argument("--day", required=True)
    r.add_argument("--output", type=Path, required=True)
    r.add_argument("--sandbox", type=Path, required=True)
    d = sub.add_parser("review")
    s = d.add_subparsers(dest="action", required=True)
    s.add_parser("list")
    r = s.add_parser("show")
    r.add_argument("observation_id")
    r = s.add_parser("assess")
    r.add_argument("observation_id")
    r.add_argument("--output", type=Path, required=True)
    r = s.add_parser("visibility")
    r.add_argument("observation_id")
    r.add_argument("--full-body", action=argparse.BooleanOptionalAction, required=True)
    r.add_argument("--reviewer", required=True)
    r.add_argument("--evidence", required=True)
    for action in ("assign", "enroll", "merge", "split", "undo"):
        r = s.add_parser(action)
        r.add_argument("id")
        r.add_argument("--reason", required=True)
        if action in ("assign", "merge"):
            r.add_argument("target")
        if action == "split":
            r.add_argument("--observations", nargs="+", required=True)
    d = sub.add_parser("portrait")
    s = d.add_subparsers(dest="action", required=True)
    r = s.add_parser("accept")
    r.add_argument("recipe_key")
    r.add_argument("--reviewer", required=True)
    r.add_argument("--evidence", required=True)
    r = s.add_parser("generate")
    r.add_argument("dog_id")
    r.add_argument("--observation", required=True)
    r.add_argument("--reserve-usd", type=float, required=True)
    r.add_argument("--build-scope")
    r.add_argument("--build-cap-usd", type=float)
    return p


def _print(value):
    print(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            default=lambda x: str(x) if isinstance(x, Path | datetime) else asdict(x),
        )
    )


def replay(settings, manifest, sandbox):
    """Offline event/observation replay with explicit local fixtures, no transports."""
    from .frigate import EventIngestor
    from .runtime import Pipeline
    from .serialization import observation_from_dict

    if manifest.is_symlink() or manifest.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("unsafe replay manifest")
    data = json.loads(manifest.read_text())
    if data.get("schema") != 1:
        raise ValueError("replay schema version required")
    root = sandbox.absolute()
    owned_path(root, "catalog.sqlite")
    if root.exists() and any(root.iterdir()):
        raise ValueError("new empty replay sandbox required")
    values = {
        **settings.values,
        "APP_DATA_ROOT": str(root),
        "PUBLISH_ENABLED": False,
        "OPENAI_GENERATION_ENABLED": False,
        "IDENTITY_MODE": "shadow",
    }
    local = Settings(values, {}, settings.config_path)
    pipe = Pipeline(local, mode="shadow")
    try:
        pipe.daily.reconcile()
        ingest = EventIngestor(pipe.store, local, pipe.clock)
        for event in data.get("events", []):
            ingest.record(event)
        observations = []
        for item in data.get("observations", []):
            item = json.loads(json.dumps(item))
            for crop in item["crops"]:
                source = (manifest.parent / crop["path"]).resolve()
                if not source.is_relative_to(manifest.parent.resolve()) or source.is_symlink():
                    raise ValueError("fixture outside manifest directory")
                dest = owned_path(root, "references/" + crop["sha256"] + ".png", create_parent=True)
                if not dest.exists():
                    shutil.copyfile(source, dest)
                    dest.chmod(0o600)
                crop["path"] = str(dest)
            observations.append(observation_from_dict(item))
        pipe._persist_observations(observations)
        return {
            "mode": "offline_replay",
            "paid_calls": 0,
            "production_publications": 0,
            "observations": len(observations),
            "status": pipe.store.status(),
            "dependent_jobs": "staged only; no network/model inference performed",
        }
    finally:
        pipe.close()


def main(argv=None):
    os.umask(0o077)
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        settings = load_settings(args.config, args.secrets_file)
        if args.data_root:
            owned_path(args.data_root, "catalog.sqlite")
            settings = replace(
                settings, values={**settings.values, "APP_DATA_ROOT": str(args.data_root)}
            )
        if args.command == "doctor":
            report = doctor(settings, live=args.mode == "live")
            _print(report)
            return (
                2
                if any(x.get("status") in ("FAIL", "BLOCKED") for x in report["checks"].values())
                else 0
            )
        if args.command == "replay":
            _print(replay(settings, args.manifest, args.sandbox))
            return 0
        if args.command == "collage":
            from .daily import DailyManager

            sandbox = args.sandbox.absolute()
            owned_path(sandbox, "catalog.sqlite")
            # Render from a protected SQLite backup and referenced assets in a sandbox;
            # no production memberships/outbox/publications can be changed.
            if sandbox.exists() and any(sandbox.iterdir()):
                raise ValueError("empty render sandbox required")
            production = Path(settings["APP_DATA_ROOT"])
            source_db = owned_path(production, "catalog.sqlite")
            if not source_db.is_file():
                raise ValueError("catalog not initialized")
            source = Store(source_db)
            try:
                source.backup(owned_path(sandbox, "catalog.sqlite", create_parent=True))
            finally:
                source.close()
            store = Store(sandbox / "catalog.sqlite")
            try:
                for row in store.db.execute(
                    "SELECT recipe_key,path FROM portraits WHERE path IS NOT NULL"
                ).fetchall():
                    source = Path(row["path"])
                    rel = source.relative_to(production)
                    dest = owned_path(sandbox, rel.as_posix(), create_parent=True)
                    shutil.copyfile(source, dest)
                    store.db.execute(
                        "UPDATE portraits SET path=? WHERE recipe_key=?",
                        (str(dest), row["recipe_key"]),
                    )
                # Existing archive receipts refer to production; render a fresh local
                # revision from membership, preserving the source catalog/archive bytes.
                store.db.execute("DELETE FROM collages")
                store.db.execute("DELETE FROM outbox")
                manager = DailyManager(
                    store,
                    replace(settings, values={**settings.values, "APP_DATA_ROOT": str(sandbox)}),
                    Clock(),
                )
                manager.reconcile()
                r = manager.build(args.day)
                if args.output.exists():
                    raise ValueError("preview output exists")
                shutil.copyfile(r.output_path, args.output)
                _print({"preview": str(args.output), "sha256": r.sha256})
            finally:
                store.close()
            return 0
        from .runtime import Pipeline

        mode = (
            args.mode
            if args.command == "run"
            else ("live" if args.command == "rollover" and args.publish else "shadow")
        )
        pipe = Pipeline(settings, mode=mode)
        try:
            if args.command == "run":
                result = pipe.run(once=args.once)
            elif args.command == "status":
                result = pipe.store.status()
            elif args.command == "backup":
                result = {
                    "database_backup": str(pipe.store.backup(args.output)),
                    "asset_root": str(pipe.root),
                    "note": "copy immutable referenced assets separately; secrets are never included",
                }
            elif args.command == "retry":
                result = {"resumed": pipe.retry_waiting()}
            elif args.command == "rollover":
                day = pipe.daily.reconcile()
                ready = pipe.store.db.execute(
                    "SELECT 1 FROM collages WHERE day=? AND revision=?",
                    (day.day, day.revision),
                ).fetchone()
                result = {
                    "day": asdict(day),
                    "composition_pending": ready is None,
                    "publication": pipe.publish_latest(),
                }
            elif args.command == "review":
                engine = pipe.identity
                if args.action == "list":
                    result = engine.review()
                elif args.action == "show":
                    row = pipe.store.db.execute(
                        "SELECT * FROM observations WHERE observation_id=?", (args.observation_id,)
                    ).fetchone()
                    if row is None:
                        raise ValueError("unknown observation")
                    result = {
                        "observation_id": row["observation_id"],
                        "camera": row["camera"],
                        "state": row["state"],
                        "dog_id": row["dog_id"],
                        "private_payload": json.loads(row["payload"]),
                    }
                elif args.action == "assess":
                    from .description.quality import LocalVisibilityAssessor

                    observation = pipe._observation(args.observation_id)
                    if args.output.exists():
                        raise ValueError("quality output exists")
                    assessor = LocalVisibilityAssessor(settings)
                    try:
                        assessments = assessor.assess_views(observation)
                    finally:
                        assessor.close()
                    with args.output.open("x") as f:
                        json.dump(
                            {
                                "observation_id": args.observation_id,
                                "assessments": [asdict(a) for a in assessments],
                            },
                            f,
                            indent=2,
                        )
                    result = {
                        "local_quality_evidence": str(args.output),
                        "automatic_acceptance": False,
                    }
                elif args.action == "visibility":
                    row = pipe.store.db.execute(
                        "SELECT state FROM observations WHERE observation_id=?",
                        (args.observation_id,),
                    ).fetchone()
                    if row is None or row["state"] != "review":
                        raise ValueError("pending observation required for visibility review")
                    if not args.reviewer.strip() or not args.evidence.strip():
                        raise ValueError("reviewer/evidence required")
                    pipe.store.audit(
                        "visibility_review",
                        {
                            "observation_id": args.observation_id,
                            "full_body": args.full_body,
                            "reviewer": args.reviewer,
                            "evidence": args.evidence,
                        },
                        pipe.clock.now().timestamp(),
                    )
                    pipe.store.enqueue(
                        "describe",
                        "visibility_recheck:" + __import__("uuid").uuid4().hex,
                        {"observation_id": args.observation_id},
                        pipe.clock.now().timestamp(),
                    )
                    result = {
                        "visibility_reviewed": args.observation_id,
                        "original_crops_preserved": True,
                    }
                elif args.action == "assign":
                    result = engine.assign(args.id, args.target, reason=args.reason)
                elif args.action == "enroll":
                    result = engine.assign(args.id, reason=args.reason)
                elif args.action == "merge":
                    result = {
                        "correction_id": engine.merge(args.id, args.target, reason=args.reason)
                    }
                elif args.action == "split":
                    result = engine.split(args.id, args.observations, reason=args.reason)
                elif args.action == "undo":
                    result = engine.undo(args.id, reason=args.reason)
            elif args.command == "portrait":
                from .portraits import PortraitService
                from .serialization import description_from_dict

                service = PortraitService(pipe.store, settings, pipe.clock)
                if args.action == "accept":
                    service.accept(args.recipe_key, reviewer=args.reviewer, evidence=args.evidence)
                    result = {"state": "validated"}
                else:
                    row = pipe.store.db.execute(
                        "SELECT payload FROM descriptions WHERE observation_id=?",
                        (args.observation,),
                    ).fetchone()
                    obs = pipe.store.db.execute(
                        "SELECT dog_id FROM observations WHERE observation_id=?",
                        (args.observation,),
                    ).fetchone()
                    if (
                        row is None
                        or obs is None
                        or not obs[0]
                        or pipe.store.canonical(obs[0]) != pipe.store.canonical(args.dog_id)
                    ):
                        raise ValueError("accepted source observation for requested dog required")
                    if args.build_scope:
                        if args.build_cap_usd is None:
                            raise ValueError("explicit build cap required")
                        service.ledger.set_build_scope(args.build_scope, args.build_cap_usd)
                    result = service.generate(
                        args.dog_id,
                        description_from_dict(json.loads(row[0])),
                        reserve_usd=args.reserve_usd,
                        build_scope=args.build_scope,
                    )
            else:
                raise ValueError("unsupported command")
            if result is not None:
                _print(result)
        finally:
            pipe.close()
        return 0
    except Exception as error:
        # All adapter errors cross this boundary without raw response/credential text.
        _print(
            {
                "error": type(error).__name__,
                "code": getattr(error, "code", "operation_failed"),
                "message": str(error)
                if isinstance(error, ConfigError)
                else "operation failed; inspect redacted readiness and operator guide",
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
