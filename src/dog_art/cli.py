"""Explicit CLI; no network or production writes during configuration/status."""

import argparse
import json
from pathlib import Path

from . import __version__
from .settings import ConfigError, load_settings


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dog-art")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", type=Path, default=Path("config/app.toml"))
    parser.add_argument("--secrets-file", type=Path, default=Path("config/.env"))
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--mode", choices=("offline", "live"), default="offline")
    doctor.add_argument("--redact", action="store_true")
    status = sub.add_parser("status")
    status.add_argument("--redact", action="store_true")
    backup = sub.add_parser("backup")
    backup.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.config, args.secrets_file)
        if args.command == "doctor":
            report = {
                "version": __version__,
                "config": str(args.config),
                "secrets_file": str(args.secrets_file),
                "secret_presence": {k: bool(v) for k, v in settings.secrets.items()},
                "readiness": {
                    s: settings.missing(s)
                    for s in ("ingest", "description", "identity", "portrait", "publish")
                },
                "network_checks": "NOT RUN",
            }
            print(json.dumps(report, indent=2))
            return 0
        from .safety import owned_path
        from .storage import Store

        store = Store(
            owned_path(Path(settings["APP_DATA_ROOT"]), "catalog.sqlite", create_parent=True)
        )
        try:
            if args.command == "status":
                print(json.dumps(store.status(), indent=2))
            elif args.command == "backup":
                print(json.dumps({"backup": str(store.backup(args.output))}))
        finally:
            store.close()
        return 0
    except (ConfigError, ValueError, OSError) as e:
        # Validation failures never echo raw values or network exception strings.
        print(
            json.dumps(
                {
                    "error": type(e).__name__,
                    "message": str(e)
                    if isinstance(e, ConfigError)
                    else "operation failed; inspect paths and readiness",
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
