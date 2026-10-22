"""Redacted readiness and actual read-only dependency probes."""

import shutil
from pathlib import Path

from . import __version__


def doctor(settings, *, live=False):
    report = {
        "version": __version__,
        "config": str(settings.config_path),
        "secret_presence": {k: bool(v) for k, v in settings.secrets.items()},
        "readiness": {
            s: settings.missing(s)
            for s in ("ingest", "description", "identity", "portrait", "publish")
        },
        "checks": {},
    }
    root = Path(settings["APP_DATA_ROOT"])
    if root.exists():
        report["free_disk_mb"] = shutil.disk_usage(root).free // 1048576
    if not live:
        report["network_checks"] = "NOT RUN"
        return report
    from .description import OllamaDescriber
    from .frigate import FrigateClient

    for stage, adapter in (("frigate", FrigateClient), ("ollama", OllamaDescriber)):
        client = None
        try:
            client = adapter(settings)
            if stage == "frigate":
                version = client.read("/version").decode().strip('"\n')
                cfg = client.json("/config")
                cameras = {
                    k: {
                        "dog_tracked": "dog"
                        in cfg["cameras"][k].get("objects", {}).get("track", []),
                        "record_enabled": cfg["cameras"][k].get("record", {}).get("enabled"),
                    }
                    for k in settings["FRIGATE_CAMERA_IDS"]
                }
                report["checks"][stage] = {
                    "status": "PASS"
                    if all(v["dog_tracked"] and v["record_enabled"] for v in cameras.values())
                    else "BLOCKED",
                    "read_access": "PASS",
                    "version": version,
                    "cameras": cameras,
                }
            else:
                report["checks"][stage] = {"status": "PASS", **client.verify_model()}
        except Exception as error:
            report["checks"][stage] = {
                "status": "FAIL",
                "code": getattr(error, "code", type(error).__name__),
            }
        finally:
            if client:
                client.close()
    if settings.get("LOCAL_IMAGE_ENCODER"):
        try:
            from .identity import OnnxImageEncoder

            encoder = OnnxImageEncoder(settings["LOCAL_IMAGE_ENCODER"])
            report["checks"]["encoder"] = {
                "status": "PASS",
                "model": encoder.manifest.model,
                "digest": encoder.manifest.sha256,
                "dimension": encoder.manifest.dimension,
                "preprocessing": encoder.preprocessing,
            }
        except Exception as error:
            report["checks"]["encoder"] = {"status": "FAIL", "code": type(error).__name__}
    report["checks"]["openai"] = {
        "status": "NOT RUN",
        "reason": "paid generation requires a separate controlled request; doctor never spends",
    }
    report["checks"]["smb"] = {
        "status": "NOT RUN",
        "reason": "mapping and controlled staging acceptance separate",
    }
    return report
