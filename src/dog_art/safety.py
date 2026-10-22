import hashlib
import json
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


class SafetyError(ValueError):
    pass


def safe_url(value: str) -> str:
    p = urlsplit(value)
    if (
        p.scheme not in ("http", "https")
        or not p.hostname
        or p.username
        or p.password
        or p.query
        or p.fragment
    ):
        raise SafetyError(
            "invalid service URL (scheme and host required; credentials/query forbidden)"
        )
    return value.rstrip("/")


def owned_path(root: Path, relative: str, *, create_parent=False) -> Path:
    if not root.is_absolute() or root == Path("/") or len(root.parts) < 3:
        raise SafetyError("narrow absolute data root required")
    if root.is_symlink() or any(p.is_symlink() for p in root.parents):
        raise SafetyError("symlink data root forbidden")
    rel = PurePosixPath(relative)
    if (
        rel.is_absolute()
        or not rel.parts
        or any(x in ("..", ".") for x in rel.parts)
        or "\\" in relative
    ):
        raise SafetyError("unsafe relative path")
    target = root.joinpath(*rel.parts)
    if not target.resolve().is_relative_to(root.resolve()) or any(
        p.is_symlink() for p in (target, *target.parents) if p != root.parent
    ):
        raise SafetyError("symlink/traversal forbidden")
    if create_parent:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    return target


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def disk_guard(root: Path, minimum_mb: int):
    if shutil.disk_usage(root).free < minimum_mb * 1024 * 1024:
        raise SafetyError("low disk: preserve retained data and last valid output")


def fingerprint(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def redact(text: str, secrets=()) -> str:
    for s in sorted((x for x in secrets if x), key=len, reverse=True):
        text = text.replace(s, "[REDACTED]")
    text = re.sub(r"https?://[^\s/@]+:[^\s/@]+@[^\s]+", "[REDACTED_URL]", text)
    text = re.sub(
        r"(?i)(authorization|password|token|api[_-]?key)\s*[:=]\s*[^\s,]+", r"\1=[REDACTED]", text
    )
    return text
