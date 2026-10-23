#!/usr/bin/env python3
"""Build deterministic runtime delivery from an explicit allowlist; never glob secrets."""

import argparse
import gzip
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def create_release(wheel, output, revision):
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("full source revision required")
    selected = {
        "wheel/" + wheel.name: wheel,
        "requirements.lock": ROOT / "requirements.lock",
        "README.md": ROOT / "README.md",
        "CODEX_BUILD_BRIEF.md": ROOT / "CODEX_BUILD_BRIEF.md",
        "ASSET_MANIFEST.json": ROOT / "ASSET_MANIFEST.json",
        "config/app.toml.example": ROOT / "config/app.toml",
        "config/app.toml": ROOT / "config/app.toml",
        "config/.env.example": ROOT / "config/.env.example",
    }
    for folder in (
        "deploy/systemd",
        "deploy/models",
        "deploy/home-assistant",
        "docs",
        "docs/evidence",
    ):
        for path in sorted((ROOT / folder).glob("*")):
            if path.is_file() and path.suffix in (".md", ".service", ".timer", ".json", ".js"):
                selected[str(path.relative_to(ROOT))] = path
    for name in (
        "bootstrap-ct112.sh",
        "provision-ct112.sh",
        "prepare-models.py",
        "verify-installed.py",
        "activate-live.template.sh",
        "install-release.sh",
        "evaluate_identity.py",
        "export_identity.py",
    ):
        p = ROOT / "scripts" / name
        if p.exists():
            selected["scripts/" + name] = p
    for folder in ("assets", "reference"):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and path.suffix in (".png", ".txt", ".py", ".md"):
                selected[str(path.relative_to(ROOT))] = path
    # Templates remain blank even if a local real dotenv exists nearby.
    for line in (ROOT / "config/.env.example").read_text().splitlines():
        if line.strip() and not line.startswith("#") and line.split("=", 1)[1].strip():
            raise ValueError("populated secrets template")
    members = {name: path.read_bytes() for name, path in selected.items()}
    # Historical specification links reference build-host files deliberately
    # excluded from runtime delivery. Keep those references pinned to source.
    for name, data in list(members.items()):
        if not name.endswith(".md"):
            continue
        doc = data.decode()
        for source_only in ("config/build.toml", ".gitignore"):
            doc = doc.replace(
                "(../" + source_only + ")",
                "(https://github.com/samueldowd/dog-art-codex/blob/"
                + revision
                + "/"
                + source_only
                + ")",
            )
        members[name] = doc.encode()
    members["SOURCE_REVISION"] = (revision + "\n").encode()
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in members.items()}
    members["SHA256SUMS"] = "".join(
        f"{digest}  {name}\n" for name, digest in sorted(manifest.items())
    ).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with (
        output.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz,
        tarfile.open(fileobj=gz, mode="w") as tar,
    ):
        for name, data in sorted(members.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if name.endswith(".sh") else 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    return {
        "path": str(output),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "members": len(members),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    print(json.dumps(create_release(args.wheel, args.output, args.source_revision), indent=2))


if __name__ == "__main__":
    main()
