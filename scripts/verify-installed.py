#!/usr/bin/env python3
"""Explicit native acceptance helper; isolated catalog, owned SMB image, no paid calls.

Run as dog-art inside the installed systemd sandbox. The caller serializes the
production worker and supplies an already reviewed generated portrait. This is
an operational fixture, never physical-dog evidence or production enrollment.
"""

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import uuid
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

from PIL import Image

from dog_art.clock import Clock, FrozenClock
from dog_art.daily import DailyManager, StalePublication, application_lock
from dog_art.description import OllamaDescriber
from dog_art.frigate import FrigateClient
from dog_art.portraits import validate_png
from dog_art.publishing import Publisher, PublishError, relative_target, validate_collage
from dog_art.publishing.transport_process import BoundedSMBTransport
from dog_art.safety import owned_path, sha256
from dog_art.settings import load_settings
from dog_art.storage import Store


def write_checkpoint(path, state):
    """A killed update leaves the previous or new complete recovery ledger."""
    temporary = path.with_name(".checkpoint-" + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x") as stream:
            stream.write(json.dumps(state, indent=2))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def restore_checkpoint(settings, root, clock, *, factory=BoundedSMBTransport):
    """Bounded maintenance restore, with a durable blocked receipt on failure."""
    pending = root / "display-checkpoint.json"
    state = json.loads(pending.read_text())
    source = owned_path(root, "display-before.png")
    data = source.read_bytes()
    validate_collage(data, state["sha256"])
    target = relative_target(settings)
    assert state["relative_path"] == target
    temporary = state.get("temporary") or str(
        Path(target).parent / (".dog-art-" + uuid.uuid4().hex + ".tmp")
    )
    assert Path(temporary).parent == Path(target).parent
    assert __import__("re").fullmatch(r"\.dog-art-[0-9a-f]{32}\.tmp", Path(temporary).name)
    state.update(state="restoration_pending", temporary=temporary)
    write_checkpoint(pending, state)
    transport = None
    try:
        transport = factory(settings)
        try:
            transport.remove_owned_temp(temporary)
        except FileNotFoundError:
            pass

        # A snapshot never restores an old day if acceptance crosses midnight.
        def current_data():
            if clock.day() == state["day"]:
                return data
            image = Image.new("RGB", (1920, 1080), settings["COLLAGE_BACKGROUND"])
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue()

        for _ in range(3):
            restored = current_data()
            transport.write_new(temporary, restored)
            digest = validate_collage(
                transport.read(temporary), hashlib.sha256(restored).hexdigest()
            )
            if current_data() != restored:
                transport.remove_owned_temp(temporary)
                continue
            transport.replace(temporary, target)
            validate_collage(transport.read(target), digest)
            if current_data() == restored:
                break
            # Midnight during replace/read must be corrected here: a stopped
            # shadow publisher cannot supply the normal waiting rollover.
        else:
            raise RuntimeError("calendar changed repeatedly during bounded restoration")
        state.update(state="restored", restored_sha256=digest, restored_day=clock.day())
        write_checkpoint(pending, state)
        return state
    except BaseException:
        state.update(state="restoration_blocked", error_code="owned_image_restore_failed")
        write_checkpoint(pending, state)
        raise RuntimeError(
            "Owned image restoration blocked; preserve display-checkpoint.json and retry restore_checkpoint under the publication lock"
        ) from None
    finally:
        if transport is not None:
            transport.close()


@contextmanager
def owned_image_checkpoint(
    settings, root, clock, *, factory=BoundedSMBTransport, baseline_day=None, baseline_sha256=None
):
    """Preserve the caller-verified current image across all helper outcomes."""
    lock = owned_path(Path(settings["APP_DATA_ROOT"]), "locks/publication.lock", create_parent=True)
    with application_lock(lock):
        captured_day = min(clock.day(), baseline_day or clock.day())
        transport = factory(settings)
        try:
            data = transport.read(relative_target(settings))
            digest = validate_collage(data)
            if baseline_sha256 is not None and digest != baseline_sha256:
                raise ValueError("owned image differs from the dated reviewed baseline")
        finally:
            transport.close()
        with (root / "display-before.png").open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        (root / "display-before.png").chmod(0o600)
        state = {
            "state": "captured",
            "day": captured_day,
            "sha256": digest,
            "relative_path": relative_target(settings),
        }
        write_checkpoint(root / "display-checkpoint.json", state)
        result = {}
        try:
            yield result
        finally:
            result.update(restore_checkpoint(settings, root, clock, factory=factory))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--secrets-file", type=Path, required=True)
    parser.add_argument("--sandbox", type=Path, required=True)
    parser.add_argument("--portrait", type=Path)
    parser.add_argument("--portrait-sha256")
    parser.add_argument("--restore-only", action="store_true")
    parser.add_argument("--baseline-day")
    parser.add_argument("--baseline-sha256")
    args = parser.parse_args()
    os.umask(0o077)
    settings = load_settings(args.config, args.secrets_file)
    root = args.sandbox.absolute()
    app_root = Path(settings["APP_DATA_ROOT"])
    if args.restore_only:
        root = owned_path(app_root, root.relative_to(app_root).as_posix())
        if not root.is_relative_to(app_root / "acceptance") or not root.is_dir():
            raise ValueError("existing application acceptance checkpoint required")
        lock = owned_path(app_root, "locks/publication.lock", create_parent=True)
        with application_lock(lock):
            print(json.dumps(restore_checkpoint(settings, root, Clock())))
        return
    if args.portrait is None or args.portrait_sha256 is None:
        parser.error("portrait and portrait-sha256 are required for acceptance")
    if args.baseline_day is None or args.baseline_sha256 is None:
        parser.error("dated reviewed baseline day and sha256 are required for acceptance")
    if (
        date.fromisoformat(args.baseline_day).isoformat() != args.baseline_day
        or args.baseline_day > Clock().day()
    ):
        raise ValueError("valid nonfuture reviewed baseline day required")
    if not root.is_relative_to(app_root / "acceptance") or root.exists():
        raise ValueError("new isolated application acceptance directory required")
    portrait = owned_path(
        app_root / "portraits", args.portrait.relative_to(app_root / "portraits").as_posix()
    )
    assert sha256(portrait) == args.portrait_sha256
    validate_png(portrait.read_bytes())
    root = owned_path(app_root, root.relative_to(app_root).as_posix(), create_parent=True)
    root.mkdir(mode=0o700)
    cfg = replace(
        settings,
        values={
            **settings.values,
            "APP_DATA_ROOT": str(root),
            "OPENAI_GENERATION_ENABLED": False,
            "PUBLISH_ENABLED": True,
        },
    )
    isolated_config = root / "app.toml"
    # JSON scalars/arrays here are valid TOML; root runtime settings are scalar/arrays.
    isolated_config.write_text(
        "\n".join(k + " = " + json.dumps(v) for k, v in cfg.values.items()) + "\n"
    )
    with owned_image_checkpoint(
        settings,
        root,
        Clock(),
        baseline_day=args.baseline_day,
        baseline_sha256=args.baseline_sha256,
    ) as restoration:
        report = exercise(args, cfg, root, portrait)
    report["display_restoration"] = restoration
    (root / "receipt.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


def exercise(args, cfg, root, portrait):
    isolated_config = root / "app.toml"
    now = Clock()
    previous = FrozenClock(now.now() - timedelta(days=1))
    art = owned_path(root, "portraits/operational-fixture.png", create_parent=True)
    shutil.copyfile(portrait, art)
    store = Store(root / "catalog.sqlite")
    try:
        store.db.execute(
            "INSERT INTO dogs VALUES('operational-fixture',?,'accepted',NULL)",
            (previous.now().timestamp(),),
        )
        store.db.execute(
            "INSERT INTO portraits(recipe_key,dog_id,recipe,state,path,sha256) VALUES('operational-fixture','operational-fixture',?,'validated',?,?)",
            (
                json.dumps(
                    {
                        "provenance": "reviewed generated-art operational fixture; not production identity"
                    }
                ),
                str(art),
                sha256(art),
            ),
        )
        old_daily = DailyManager(store, cfg, previous)
        old_daily.reconcile()
        old_daily.record_sighting("operational-fixture", [previous.now()])
        old_revision = old_daily.build()
        retained = {p: sha256(p) for p in (root / "archives").rglob("*") if p.is_file()}
        retained[art] = sha256(art)
    finally:
        store.close()

    command = [
        str(Path(sys.executable).parent / "dog-art"),
        "--config",
        str(isolated_config),
        "--secrets-file",
        str(args.secrets_file),
        "rollover",
        "--publish",
    ]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    rollover_state = None
    for _ in range(2):
        # Actual installed CLI, wall clock and network publisher. No host clock change.
        subprocess.run(command, check=True, timeout=90, capture_output=True, env=env)
        check = Store(root / "catalog.sqlite")
        try:
            latest = DailyManager(check, cfg, now).latest()
            snapshot = (
                latest.day,
                latest.generation,
                latest.revision,
                latest.sha256,
                check.db.execute("SELECT count(*) FROM collages").fetchone()[0],
            )
            if rollover_state is not None:
                assert snapshot == rollover_state
            rollover_state = snapshot
        finally:
            check.close()
    store = Store(root / "catalog.sqlite")
    try:
        daily = DailyManager(store, cfg, now)
        blank = daily.latest()
        assert blank.day == now.day() and blank.dog_ids == ()
        assert all(sha256(path) == digest for path, digest in retained.items())
        try:
            Publisher(store, cfg, now, daily).publish(old_revision)
        except PublishError:
            # Publisher deliberately redacts a stale guard into PublishError.
            try:
                with daily.publication_guard(old_revision):
                    raise AssertionError("old-day guard unexpectedly admitted publication")
            except StalePublication:
                pass
        else:
            raise AssertionError("old-day publication was accepted")
        daily.record_sighting("operational-fixture", [now.now()])
        restored = daily.build()
        unavailable = replace(cfg, values={**cfg.values, "SMB_HOST": "127.0.0.1", "SMB_PORT": 1})
        try:
            Publisher(store, unavailable, now, daily).publish(restored)
        except (PublishError, OSError):
            pass
        else:
            raise AssertionError("unavailable SMB endpoint unexpectedly succeeded")
        receipt = Publisher(store, cfg, now, daily).publish(restored)
        assert receipt.sha256 == restored.sha256 and receipt.state == "verified"
        assert all(sha256(path) == digest for path, digest in retained.items())
        # Connection-refusal exercises are local only; no service/network/security changes.
        for kind in ("frigate", "ollama"):
            values = (
                {
                    **cfg.values,
                    "FRIGATE_BASE_URL": "http://127.0.0.1:1",
                    "FRIGATE_AUTH_MODE": "none",
                }
                if kind == "frigate"
                else {**cfg.values, "OLLAMA_BASE_URL": "http://127.0.0.1:1"}
            )
            bad = replace(cfg, values=values, secrets={})
            adapter = FrigateClient(bad) if kind == "frigate" else OllamaDescriber(bad)
            failed = False
            try:
                adapter.json("/version") if kind == "frigate" else adapter.verify_model()
            except Exception:
                failed = True
            finally:
                adapter.close()
            assert failed, "unavailable local endpoint unexpectedly succeeded"
        source = FrigateClient(cfg)
        model = OllamaDescriber(cfg)
        try:
            assert isinstance(
                source.events(
                    after=now.now().timestamp() - 3600, before=now.now().timestamp(), limit=1
                ),
                list,
            )
            model.verify_model()
        finally:
            source.close()
            model.close()
        report = {
            "mode": "actual installed CLI operational fixture",
            "day": now.day(),
            "previous_day": old_revision.day,
            "blank_sha256": blank.sha256,
            "restored_sha256": receipt.sha256,
            "retained_files": len(retained),
            "rollover_idempotent": True,
            "old_day_rejected": True,
            "smb_refusal_then_recovery": True,
            "frigate_and_ollama_refusal_then_metadata_recovery": True,
            "hardening": "caller must verify systemd sandbox independently",
            "production_catalog_changed": False,
            "paid_calls": 0,
            "limitations": "isolated fixture catalog; not natural midnight, full upstream outage, or identity acceptance",
        }
        (root / "receipt.json").write_text(json.dumps(report, indent=2))
        return report
    finally:
        store.close()


if __name__ == "__main__":
    main()
