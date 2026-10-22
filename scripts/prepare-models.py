#!/usr/bin/env python3
"""Explicit build/installation preparation; runtime never imports or downloads here."""

import argparse
import hashlib
import json
import math
import os
import shutil
import signal
import stat
import threading
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path

MODELS = (
    (
        "encoder.json",
        "dinov2-small.onnx",
        88532934,
        "f22797eabf810a75e41de68d378541ebea372122b25c4ce3ef25ff618250c20a",
        "https://huggingface.co/onnx-community/dinov2-small/resolve/8b1f705a3a7f6f062f6bdd21986c1583d3ef105d/onnx/model.onnx",
    ),
    (
        "detector.json",
        "yolox_nano.onnx",
        3659407,
        "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d",
        "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx",
    ),
)


class HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            raise ValueError("non-HTTPS model redirect rejected")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@contextmanager
def download_deadline(seconds):
    # Explicit preparation targets Unix Python on Debian/macOS, on the main thread.
    if threading.current_thread() is not threading.main_thread():
        raise ValueError("model preparation must run on the main thread")
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("positive finite model deadline required")
    previous = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    if any(previous_timer):
        raise ValueError("existing alarm prevents independent model deadline")

    def expired(signum, frame):
        raise TimeoutError("model total download deadline exceeded")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def file_hash(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(65536):
            checksum.update(block)
    return checksum.hexdigest()


def prepare(directory, manifests, *, max_mb=500, opener=None, timeout_seconds=180):
    root = Path(directory).absolute()
    if root.is_symlink() or len(root.parts) < 4 or root.resolve() != root:
        raise ValueError("narrow non-symlink preparation directory required")
    if not isinstance(max_mb, int) or max_mb <= 0 or sum(m[2] for m in MODELS) > max_mb * 1048576:
        raise ValueError("model download allowance exceeded")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    opener = opener or urllib.request.build_opener(HTTPSRedirects()).open
    for manifest_name, name, size, digest, source in MODELS:
        manifest_path = Path(manifests) / manifest_name
        if (
            manifest_path.is_symlink()
            or not manifest_path.is_file()
            or manifest_path.stat().st_size > 65536
        ):
            raise ValueError("regular bounded model manifest required")
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        if manifest["sha256"] != digest or manifest["path"] != name or manifest["source"] != source:
            raise ValueError("model manifest differs from pinned specification")
        dest = root / name
        target = root / manifest_name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError("regular manifest destination required")
        if target.exists() and target.read_bytes() != manifest_bytes:
            raise ValueError("existing manifest differs; preserve and inspect")
        if dest.is_symlink() or (dest.exists() and not stat.S_ISREG(dest.stat().st_mode)):
            raise ValueError("model destination symlink forbidden")
        if dest.exists():
            if dest.stat().st_size != size or file_hash(dest) != digest:
                raise ValueError("existing model differs; preserve and inspect")
        else:
            if shutil.disk_usage(root).free < size + 2048 * 1048576:
                raise ValueError("preserve configured disk floor during preparation")
            temp = root / (".model-" + uuid.uuid4().hex + ".part")
            received = 0
            checksum = hashlib.sha256()
            try:
                # Hash/byte bounds and verified HTTPS apply only to explicit build preparation.
                with (
                    download_deadline(timeout_seconds),
                    opener(source, timeout=30) as response,
                    os.fdopen(
                        os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
                    ) as out,
                ):
                    if not response.geturl().startswith("https://"):
                        raise ValueError("non-HTTPS model redirect rejected")
                    while chunk := response.read(65536):
                        received += len(chunk)
                        if received > size:
                            raise ValueError("model byte bound exceeded")
                        checksum.update(chunk)
                        out.write(chunk)
                if received != size or checksum.hexdigest() != digest:
                    raise ValueError("model checksum/length mismatch")
                temp.chmod(0o600)
                try:
                    os.link(temp, dest)
                except FileExistsError:
                    if (
                        dest.is_symlink()
                        or not dest.is_file()
                        or dest.stat().st_size != size
                        or file_hash(dest) != digest
                    ):
                        raise ValueError("concurrent model differs; preserve and inspect")
            finally:
                temp.unlink(missing_ok=True)
        if not target.exists():
            with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
                f.write(manifest_bytes)
    return {
        "models": len(MODELS),
        "total_bytes": sum(m[2] for m in MODELS),
        "private_images": False,
    }


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser()
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument(
        "--manifests", type=Path, default=Path(__file__).resolve().parents[1] / "deploy/models"
    )
    p.add_argument("--max-mb", type=int, default=500)
    a = p.parse_args()
    print(json.dumps(prepare(a.directory, a.manifests, max_mb=a.max_mb)))


if __name__ == "__main__":
    main()
