import hashlib
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from dog_art.clock import FrozenClock
from dog_art.contracts import CollageRevision
from dog_art.publishing import Publisher, PublishError, relative_target
from dog_art.settings import Settings
from dog_art.storage import Store


class MemorySMB:
    def __init__(self):
        self.files = {"kitchen-tv/dog-art/unrelated.png": b"sentinel"}
        self.fail_replace = False
        self.replacements = 0

    def read(self, p):
        if p not in self.files:
            raise FileNotFoundError(p)
        return self.files[p]

    def write_new(self, p, data):
        assert p not in self.files
        self.files[p] = data

    def replace(self, a, b):
        if self.fail_replace:
            raise PermissionError("open handle")
        self.files[b] = self.files.pop(a)
        self.replacements += 1

    def remove_owned_temp(self, p):
        self.files.pop(p, None)


class Guard:
    stale = False

    def revalidate(self, *, db=None):
        if self.stale:
            raise PublishError("stale generation")

    @contextmanager
    def publication_guard(self, revision):
        yield self


def setup(tmp_path):
    settings = Settings(
        {
            "SMB_HOST": "ha.example",
            "SMB_SHARE": "media",
            "SMB_SUBDIRECTORY": "kitchen-tv/dog-art",
            "PUBLISH_FILENAME": "dog-collage.png",
            "PUBLISH_ENABLED": True,
        },
        {"SMB_USERNAME": "test", "SMB_PASSWORD": "sentinel-secret"},
    )
    clock = FrozenClock(datetime(2026, 10, 22, 12, tzinfo=UTC))
    store = Store(tmp_path / "db.sqlite")
    output = tmp_path / "collage.png"
    Image.new("RGB", (1920, 1080), "#F3EBDD").save(output)
    revision = CollageRevision(
        "2026-10-22",
        "generation",
        1,
        (),
        (),
        1,
        (),
        1920,
        1080,
        "#F3EBDD",
        output,
        hashlib.sha256(output.read_bytes()).hexdigest(),
        clock.now(),
    )
    smb = MemorySMB()
    guard = Guard()
    return Publisher(store, settings, clock, guard, transport=smb), smb, guard, revision, store


def test_replace_readback_and_recovery(tmp_path):
    pub, smb, guard, revision, store = setup(tmp_path)
    receipt = pub.publish(revision)
    assert receipt.sha256 == revision.sha256
    assert smb.files["kitchen-tv/dog-art/unrelated.png"] == b"sentinel"
    pub.publish(revision)
    assert smb.replacements == 1
    assert not any(x.endswith(".tmp") for x in smb.files)
    store.close()


def test_denied_replace_preserves_old_and_stale_guard(tmp_path):
    pub, smb, guard, revision, store = setup(tmp_path)
    target = "kitchen-tv/dog-art/dog-collage.png"
    smb.files[target] = b"old"
    smb.fail_replace = True
    with pytest.raises(PublishError):
        pub.publish(revision)
    assert (
        smb.files[target] == b"old" and smb.files["kitchen-tv/dog-art/unrelated.png"] == b"sentinel"
    )
    smb.fail_replace = False
    guard.stale = True
    with pytest.raises(PublishError, match="stale"):
        pub.publish(revision)
    assert smb.files[target] == b"old"
    store.close()


def test_path_traversal():
    settings = Settings(
        {
            "SMB_HOST": "ha",
            "SMB_SHARE": "media",
            "SMB_SUBDIRECTORY": "../other",
            "PUBLISH_FILENAME": "dog-collage.png",
        }
    )
    with pytest.raises(PublishError):
        relative_target(settings)


class HungTransport:
    def __init__(self, settings):
        pass

    def read(self, path):
        import time

        time.sleep(60)

    def close(self):
        pass


def test_hung_smb_worker_is_killed_and_returns_control():
    import time

    from dog_art.publishing.transport_process import BoundedSMBTransport, TransportTimeout

    start = time.monotonic()
    transport = BoundedSMBTransport(Settings({}), timeout=3, factory=HungTransport)
    with pytest.raises(TransportTimeout):
        transport.read("owned.png")
    assert time.monotonic() - start < 6
    assert not transport.process.is_alive()


def test_hung_publish_releases_real_rollover_barrier(tmp_path):
    import time
    from dataclasses import replace

    from dog_art.daily import DailyManager
    from dog_art.publishing.transport_process import BoundedSMBTransport
    from dog_art.settings import load_settings

    cfg = load_settings(
        Path(__file__).resolve().parents[1] / "config/app.toml", tmp_path / ".env", environ={}
    )
    settings = replace(
        cfg,
        values={
            **cfg.values,
            "APP_DATA_ROOT": str(tmp_path / "state"),
            "MIN_FREE_DISK_MB": 0,
            "PUBLISH_ENABLED": True,
            "SMB_HOST": "ha.example",
        },
        secrets={"SMB_USERNAME": "test", "SMB_PASSWORD": "sentinel"},
    )
    store = Store(tmp_path / "state/catalog.sqlite")
    clock = FrozenClock(datetime(2026, 10, 22, 12, tzinfo=UTC))
    daily = DailyManager(store, settings, clock)
    daily.reconcile()
    revision = daily.latest()
    transport = BoundedSMBTransport(settings, timeout=3, factory=HungTransport)
    publisher = Publisher(store, settings, clock, daily, transport=transport)
    with pytest.raises(PublishError):
        publisher.publish(revision)
    start = time.monotonic()
    clock.value = datetime(2026, 10, 23, 5, tzinfo=UTC)
    daily.reconcile()
    assert time.monotonic() - start < 1 and daily.latest().day == "2026-10-23"
    store.close()


class LostUploadAck(MemorySMB):
    def __init__(self):
        super().__init__()
        self.lose = True
        self.created = []

    def write_new(self, path, data):
        super().write_new(path, data)
        self.created.append(path)
        if self.lose:
            raise TimeoutError("ack lost after remote creation")


def test_lost_upload_ack_is_cleaned_from_durable_ledger_on_restart(tmp_path):
    pub, _, guard, revision, store = setup(tmp_path)
    smb = LostUploadAck()
    pub.transport = smb
    with pytest.raises(PublishError):
        pub.publish(revision)
    orphan = smb.created[0]
    assert orphan in smb.files
    dbpath = store.path
    store.close()
    restarted = Store(dbpath)
    pub = Publisher(restarted, pub.settings, pub.clock, guard, transport=smb)
    smb.lose = False
    pub.publish(revision)
    assert orphan not in smb.files
    assert not any(p.endswith(".tmp") for p in smb.files)
    assert smb.files["kitchen-tv/dog-art/unrelated.png"] == b"sentinel"
    restarted.close()


class BrokenConnect:
    def __init__(self, settings):
        raise OSError("test connection refused")


def test_failed_transport_constructor_reaps_child():
    import multiprocessing

    from dog_art.publishing.transport_process import BoundedSMBTransport

    before = {p.pid for p in multiprocessing.active_children()}
    with pytest.raises(OSError):
        BoundedSMBTransport(Settings({}), timeout=3, factory=BrokenConnect)
    assert {p.pid for p in multiprocessing.active_children()} <= before


def test_smb_missing_file_errno_is_normalized_without_masking_denial():
    from types import SimpleNamespace

    from smbprotocol.exceptions import SMBOSError
    from smbprotocol.header import NtStatus

    from dog_art.publishing import SMBTransport

    transport = object.__new__(SMBTransport)
    transport.settings = Settings({"SMB_HOST": "ha", "SMB_SHARE": "media"})
    transport.cache = {}

    def missing(*args, **kwargs):
        raise SMBOSError(NtStatus.STATUS_OBJECT_NAME_NOT_FOUND, "private path")

    transport.client = SimpleNamespace(open_file=missing, remove=missing)
    with pytest.raises(FileNotFoundError):
        transport.read("kitchen-tv/dog-art/owned.png")
    with pytest.raises(FileNotFoundError):
        transport.remove_owned_temp("kitchen-tv/dog-art/.dog-art-test.tmp")

    def denied(*args, **kwargs):
        raise SMBOSError(NtStatus.STATUS_ACCESS_DENIED, "private path")

    transport.client.open_file = denied
    with pytest.raises(SMBOSError):
        transport.read("kitchen-tv/dog-art/owned.png")
