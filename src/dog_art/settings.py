"""Strict three-file configuration. Never execute or interpolate dotenv content."""

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .config_schema import SCHEMAS
from .safety import SafetyError, safe_url

SECRET_KEYS = frozenset(
    (
        "FRIGATE_USERNAME",
        "FRIGATE_PASSWORD",
        "FRIGATE_TOKEN",
        "MQTT_USERNAME",
        "MQTT_PASSWORD",
        "OLLAMA_API_KEY",
        "OPENAI_API_KEY",
        "SMB_USERNAME",
        "SMB_PASSWORD",
    )
)


class ConfigError(ValueError):
    pass


def load_toml(path: Path, kind: str) -> dict:
    try:
        values = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        raise ConfigError(f"cannot parse {kind} configuration") from None
    schema = SCHEMAS[kind]
    unknown = set(values) - schema.keys()
    if unknown:
        raise ConfigError(f"unknown or misplaced {kind} keys: {', '.join(sorted(unknown))}")
    for k, v in values.items():
        if v == "":
            continue
        typ = schema[k]
        valid = (
            typ == "string"
            and isinstance(v, str)
            or typ == "integer"
            and type(v) is int
            or typ == "number"
            and type(v) in (int, float)
            or typ == "boolean"
            and type(v) is bool
            or typ == "array[string]"
            and isinstance(v, list)
            and all(isinstance(x, str) for x in v)
        )
        if not valid:
            raise ConfigError(f"{k}: expected {typ}")
        if typ in ("integer", "number") and (v < 0 or not __import__("math").isfinite(v)):
            raise ConfigError(f"{k}: finite nonnegative value required")
    for k in ("FRIGATE_BASE_URL", "OLLAMA_BASE_URL", "GIT_REMOTE_URL"):
        if values.get(k):
            try:
                safe_url(values[k])
            except SafetyError:
                raise ConfigError(f"{k}: valid credential-free URL required") from None
    return values


def load_secrets(path: Path, environ=None) -> dict:
    from dotenv import dotenv_values

    if not path.exists():
        parsed = {}
    else:
        names = []
        for line in path.read_text().splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            m = re.match(r"([A-Z_]+)\s*=", s)
            if not m:
                raise ConfigError("malformed secrets file (KEY=value required)")
            names.append(m[1])
        if len(names) != len(set(names)):
            raise ConfigError("duplicate secret keys")
        if set(names) - SECRET_KEYS:
            raise ConfigError("unknown or misplaced secret keys")
        parsed = dict(dotenv_values(path, interpolate=False))
    env = os.environ if environ is None else environ
    return {k: env[k] if k in env else (parsed.get(k) or "") for k in SECRET_KEYS}


@dataclass(frozen=True)
class Settings:
    values: dict
    secrets: dict = field(default_factory=dict, repr=False)
    config_path: Path | None = None

    def __getitem__(self, key):
        return self.values[key]

    def get(self, key, default=None):
        return self.values.get(key, default)

    def missing(self, stage: str) -> list[str]:
        required = {
            "ingest": ["FRIGATE_BASE_URL", "FRIGATE_AUTH_MODE", "FRIGATE_CAMERA_IDS"],
            "description": ["OLLAMA_BASE_URL", "OLLAMA_MODEL"],
            "identity": [
                "LOCAL_IMAGE_ENCODER",
                "IDENTITY_MATCH_THRESHOLD",
                "IDENTITY_NEW_THRESHOLD",
                "IDENTITY_SCORE_MARGIN",
                "IDENTITY_CALIBRATION_PATH",
            ],
            "portrait": [
                "OPENAI_IMAGE_MODEL",
                "OPENAI_DAILY_BUDGET_USD",
                "OPENAI_MAX_CALLS_PER_DAY",
            ],
            "publish": ["SMB_HOST", "SMB_SHARE", "SMB_SUBDIRECTORY", "PUBLISH_FILENAME"],
        }.get(stage, [])
        if stage == "identity" and self.get("IDENTITY_MODE") == "per_observation":
            required = ["LOCAL_IMAGE_ENCODER"]
        result = [k for k in required if self.values.get(k) in ("", None, [])]
        if stage == "portrait":
            if (
                "OPENAI_PORTRAIT_RESERVATION_USD" in self.values
                and self.values["OPENAI_PORTRAIT_RESERVATION_USD"] == ""
            ):
                result.append("OPENAI_PORTRAIT_RESERVATION_USD")
            if not self.get("OPENAI_GENERATION_ENABLED"):
                result.append("OPENAI_GENERATION_ENABLED")
            if not self.secrets.get("OPENAI_API_KEY"):
                result.append("OPENAI_API_KEY")
        if stage == "publish":
            if not self.get("PUBLISH_ENABLED"):
                result.append("PUBLISH_ENABLED")
            result += [k for k in ("SMB_USERNAME", "SMB_PASSWORD") if not self.secrets.get(k)]
        return result


def load_settings(config: Path, secrets_file: Path, *, environ=None) -> Settings:
    values = load_toml(config, "app")
    secrets = load_secrets(secrets_file, environ)
    if values.get("IDENTITY_MODE") not in ("shadow", "calibrated_auto", "per_observation"):
        raise ConfigError("unsupported IDENTITY_MODE")
    if values.get("PORTRAIT_REVIEW_MODE", "operator") not in ("operator", "local_vlm"):
        raise ConfigError("unsupported PORTRAIT_REVIEW_MODE")
    if values.get("COLLAGE_PORTRAIT_POLICY", "all_accepted") not in (
        "all_accepted",
        "approved_only",
    ):
        raise ConfigError("unsupported COLLAGE_PORTRAIT_POLICY")
    reservation = values.get("OPENAI_PORTRAIT_RESERVATION_USD")
    daily_budget = values.get("OPENAI_DAILY_BUDGET_USD")
    if reservation not in (None, "") and (
        reservation <= 0 or (daily_budget not in (None, "") and reservation > daily_budget)
    ):
        raise ConfigError("portrait reservation must be positive and within daily budget")
    policy = values.get("SOURCE_REFERENCE_POLICY", "full_body")
    if policy not in ("full_body", "best_effort_partial"):
        raise ConfigError("unsupported SOURCE_REFERENCE_POLICY")
    if policy == "best_effort_partial" and values.get("IDENTITY_MODE") != "per_observation":
        raise ConfigError("partial references require per_observation mode")
    if values.get("FRIGATE_AUTH_MODE") not in ("", "none", "bearer", "session", "basic"):
        raise ConfigError("unsupported FRIGATE_AUTH_MODE")
    mode = values.get("FRIGATE_AUTH_MODE")
    if mode == "bearer" and (secrets["FRIGATE_USERNAME"] or secrets["FRIGATE_PASSWORD"]):
        raise ConfigError("Frigate token/password modes are exclusive")
    if mode in ("session", "basic") and secrets["FRIGATE_TOKEN"]:
        raise ConfigError("Frigate token/password modes are exclusive")
    if (
        values.get("ALLOW_CAMERA_CROP_UPLOAD")
        or values.get("OPENAI_REFERENCE_MODE") != "artwork_only"
    ):
        raise ConfigError(
            "camera upload unsupported until separately reviewed isolation policy is implemented"
        )
    if (values.get("COLLAGE_WIDTH"), values.get("COLLAGE_HEIGHT")) != (1920, 1080):
        raise ConfigError("collage must be 1920x1080")
    return Settings(values, secrets, config)
