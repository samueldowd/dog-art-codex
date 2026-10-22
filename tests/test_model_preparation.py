"""Exercise explicit model preparation without network or actual large weights."""

import hashlib
import importlib.util
import io
import json
import signal
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_models", ROOT / "scripts/prepare-models.py")
preparation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparation)


@pytest.fixture
def setup_model(tmp_path, monkeypatch):
    data = b"hash-pinned fake model"
    digest = hashlib.sha256(data).hexdigest()
    source = "https://example.invalid/pinned-model"
    monkeypatch.setattr(
        preparation, "MODELS", (("encoder.json", "model.onnx", len(data), digest, source),)
    )
    monkeypatch.setattr(
        preparation.shutil, "disk_usage", lambda _: SimpleNamespace(free=4 * 1024**3)
    )
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    manifest = manifests / "encoder.json"
    manifest.write_text(json.dumps({"path": "model.onnx", "sha256": digest, "source": source}))
    return tmp_path / "models", manifests, data


class Response(io.BytesIO):
    def geturl(self):
        return "https://example.invalid/pinned-model"


def test_prepare_verified_reuse_and_permissions(setup_model):
    root, manifests, data = setup_model
    calls = []

    def opener(url, timeout):
        calls.append(url)
        return Response(data)

    receipt = preparation.prepare(root, manifests, opener=opener)
    assert receipt["total_bytes"] == len(data)
    assert (root / "model.onnx").read_bytes() == data
    assert (root / "model.onnx").stat().st_mode & 0o777 == 0o600
    assert root.stat().st_mode & 0o777 == 0o700
    preparation.prepare(root, manifests, opener=opener)
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [b"short", b"x" * 21, b"x" * 22])
def test_corrupt_truncated_oversized_download_never_installed(setup_model, payload):
    root, manifests, _ = setup_model
    with pytest.raises(ValueError, match="checksum/length|byte bound"):
        preparation.prepare(root, manifests, opener=lambda *a, **k: Response(payload))
    assert list(root.iterdir()) == []


def test_total_deadline_interrupts_blocked_read_and_cleans_partial(setup_model):
    root, manifests, data = setup_model

    class Slow(Response):
        def read(self, n):
            time.sleep(1)
            return super().read(n)

    previous = signal.getsignal(signal.SIGALRM)
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="total download deadline"):
        preparation.prepare(
            root, manifests, opener=lambda *a, **k: Slow(data), timeout_seconds=0.03
        )
    assert time.monotonic() - started < 0.5
    assert signal.getsignal(signal.SIGALRM) == previous
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("identical", [False, True])
def test_concurrent_destination_preserved(setup_model, identical):
    root, manifests, data = setup_model
    winner = data if identical else b"different process owns these bytes"

    def opener(*a, **k):
        (root / "model.onnx").write_bytes(winner)
        return Response(data)

    if identical:
        preparation.prepare(root, manifests, opener=opener)
    else:
        with pytest.raises(ValueError, match="concurrent model differs"):
            preparation.prepare(root, manifests, opener=opener)
    assert (root / "model.onnx").read_bytes() == winner
    assert not list(root.glob("*.part"))


@pytest.mark.parametrize(
    "kind", ["weight_symlink", "manifest_symlink", "manifest_differs", "source_differs"]
)
def test_protected_paths_and_provenance_fail_before_request(setup_model, kind):
    root, manifests, data = setup_model
    root.mkdir()
    sentinel = root.parent / "sentinel"
    sentinel.write_bytes(b"preserve")
    if kind == "weight_symlink":
        (root / "model.onnx").symlink_to(sentinel)
    elif kind == "manifest_symlink":
        (root / "encoder.json").symlink_to(sentinel)
    elif kind == "manifest_differs":
        (root / "encoder.json").write_bytes(b"preserve")
    else:
        p = manifests / "encoder.json"
        p.write_text(p.read_text().replace("example.invalid", "other.invalid"))

    def denied(*a, **k):
        pytest.fail("protected path/provenance failure attempted network")

    with pytest.raises(ValueError):
        preparation.prepare(root, manifests, opener=denied)
    assert sentinel.read_bytes() == b"preserve"


def test_allowance_fails_without_request_or_directory(setup_model):
    root, manifests, _ = setup_model
    with pytest.raises(ValueError, match="allowance exceeded"):
        preparation.prepare(root, manifests, max_mb=0)
    assert not root.exists()


def test_https_redirect_rejected_before_following():
    request = urllib.request.Request("https://example.invalid/model")
    with pytest.raises(ValueError, match="non-HTTPS"):
        preparation.HTTPSRedirects().redirect_request(
            request, None, 302, "Found", {}, "http://example.invalid/model"
        )
