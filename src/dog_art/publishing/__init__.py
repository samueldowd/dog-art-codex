"""Only the owned image is replaced. SMB credentials remain inside session setup."""

import hashlib
import io
import json
import re
import uuid
from dataclasses import asdict
from pathlib import PurePosixPath

from PIL import Image

from ..contracts import PublishReceipt


class PublishError(ValueError):
    pass


def relative_target(settings):
    host = settings.get("SMB_HOST", "")
    share = settings.get("SMB_SHARE", "")
    sub = settings.get("SMB_SUBDIRECTORY", "")
    name = settings.get("PUBLISH_FILENAME", "")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host) or not re.fullmatch(r"[A-Za-z0-9_-]+", share):
        raise PublishError("explicit valid SMB host/share required")
    p = PurePosixPath(sub)
    if (
        not sub
        or p.is_absolute()
        or any(x in (".", "..") for x in p.parts)
        or "\\" in sub
        or ":" in sub
    ):
        raise PublishError("narrow relative SMB subdirectory required")
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.png", name):
        raise PublishError("single owned PNG filename required")
    return str(p / name)


def validate_collage(data, expected_hash=None):
    if len(data) > 32 * 1024 * 1024:
        raise PublishError("collage byte limit")
    digest = hashlib.sha256(data).hexdigest()
    if expected_hash and digest != expected_hash:
        raise PublishError("collage checksum mismatch")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "PNG" or image.size != (1920, 1080) or image.mode != "RGB":
                raise PublishError("opaque RGB 1920x1080 PNG required")
            image.load()
    except PublishError:
        raise
    except Exception:
        raise PublishError("collage decode failed") from None
    return digest


class SMBTransport:
    def __init__(self, settings):
        import smbclient

        self.client = smbclient
        self.settings = settings
        self.relative = relative_target(settings)
        username = settings.secrets.get("SMB_USERNAME")
        password = settings.secrets.get("SMB_PASSWORD")
        if not username or not password:
            raise PublishError("SMB credentials required")
        if settings.get("SMB_DOMAIN"):
            username = settings["SMB_DOMAIN"] + "\\" + username
        # Signing and encryption required; never fall back to SMB1 or anonymous.
        self.cache = {}
        self.client.register_session(
            settings["SMB_HOST"],
            username=username,
            password=password,
            port=settings["SMB_PORT"],
            encrypt=True,
            require_signing=True,
            connection_timeout=10,
            connection_cache=self.cache,
        )

    def unc(self, relative):
        # All callers provide only the owned final path or a generated temporary sibling.
        return (
            "\\\\"
            + self.settings["SMB_HOST"]
            + "\\"
            + self.settings["SMB_SHARE"]
            + "\\"
            + relative.replace("/", "\\")
        )

    def read(self, relative):
        try:
            with self.client.open_file(
                self.unc(relative), mode="rb", connection_cache=self.cache
            ) as f:
                return f.read(32 * 1024 * 1024 + 1)
        except OSError as error:
            # smbprotocol.SMBOSError carries ENOENT but is not a Python
            # FileNotFoundError. Normalize only that exact missing-file state.
            if error.errno == 2:
                raise FileNotFoundError("owned remote image missing") from None
            raise

    def write_new(self, relative, data):
        with self.client.open_file(self.unc(relative), mode="xb", connection_cache=self.cache) as f:
            f.write(data)
            f.flush()

    def replace(self, source, target):
        self.client.replace(self.unc(source), self.unc(target), connection_cache=self.cache)

    def remove_owned_temp(self, relative):
        if not PurePosixPath(relative).name.startswith(".dog-art-") or not relative.endswith(
            ".tmp"
        ):
            raise PublishError("not owned staging path")
        try:
            self.client.remove(self.unc(relative), connection_cache=self.cache)
        except OSError as error:
            if error.errno == 2:
                raise FileNotFoundError("owned remote staging file missing") from None
            raise

    def close(self):
        self.client.reset_connection_cache(connection_cache=self.cache)


class Publisher:
    def __init__(self, store, settings, clock, daily, *, transport=None):
        self.store = store
        self.settings = settings
        self.clock = clock
        self.daily = daily
        self.transport = transport

    def _temp_key(self, target):
        scope = "/".join((self.settings["SMB_HOST"], self.settings["SMB_SHARE"], target))
        return "smb_pending_temps:" + hashlib.sha256(scope.encode()).hexdigest()

    def _pending(self, key, target):
        row = self.store.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        paths = json.loads(row[0]) if row else []
        parent = PurePosixPath(target).parent
        if not isinstance(paths, list) or any(
            not isinstance(p, str)
            or PurePosixPath(p).parent != parent
            or not re.fullmatch(r"\.dog-art-[a-f0-9]{32}\.tmp", PurePosixPath(p).name)
            for p in paths
        ):
            raise PublishError("invalid owned staging cleanup ledger")
        return paths

    def _remember(self, key, paths):
        self.store.db.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, json.dumps(paths))
        )

    def _cleanup(self, transport, key, target):
        for path in self._pending(key, target):
            try:
                transport.remove_owned_temp(path)
            except FileNotFoundError:
                pass
            # A lost acknowledgement remains durable for the next attempt. Never
            # accumulate new UUIDs while an old cleanup cannot be reconciled.
            self._remember(key, [p for p in self._pending(key, target) if p != path])

    def publish(self, revision):
        if self.settings.missing("publish"):
            raise PublishError("publication not enabled/ready")
        target = relative_target(self.settings)
        data = revision.output_path.read_bytes()
        validate_collage(data, revision.sha256)
        from .transport_process import BoundedSMBTransport

        transport = self.transport or BoundedSMBTransport(self.settings)
        temp = str(PurePosixPath(target).parent / (".dog-art-" + uuid.uuid4().hex + ".tmp"))
        key = self._temp_key(target)
        try:
            # Guard serializes other publishers and day rollover. Revalidate at the last
            # safe point before replacement; bounded transport calls prevent infinite lock.
            with self.daily.publication_guard(revision) as guard:
                self._cleanup(transport, key, target)
                try:
                    remote = transport.read(target)
                except FileNotFoundError:
                    remote = None
                uploaded = self.clock.now()
                if remote is None or hashlib.sha256(remote).hexdigest() != revision.sha256:
                    self._remember(key, [temp])
                    transport.write_new(temp, data)
                    validate_collage(transport.read(temp), revision.sha256)
                    guard.revalidate()
                    transport.replace(temp, target)
                    self._remember(key, [])
                else:
                    guard.revalidate()
                replaced = self.clock.now()
                validate_collage(transport.read(target), revision.sha256)
                guard.revalidate()
                receipt = PublishReceipt(
                    revision.generation,
                    revision.revision,
                    revision.sha256,
                    self.settings["SMB_HOST"],
                    self.settings["SMB_SHARE"],
                    target,
                    uploaded,
                    replaced,
                    self.clock.now(),
                )
                payload = asdict(receipt)
                for k in ("uploaded_at", "replaced_at", "verified_at"):
                    payload[k] = payload[k].isoformat()
                with self.store.transaction() as db:
                    # Bind the receipt to the same committed readiness snapshot.
                    # A local approval can finish after readback revalidation.
                    guard.revalidate(db=db)
                    db.execute(
                        "INSERT INTO publications VALUES(?,?,?)",
                        (
                            uuid.uuid4().hex,
                            self.clock.now().timestamp(),
                            json.dumps(payload, sort_keys=True),
                        ),
                    )
                    db.execute(
                        "UPDATE outbox SET state='published' WHERE day=? AND revision=? AND generation=?",
                        (revision.day, revision.revision, revision.generation),
                    )
                return receipt
        except PublishError:
            raise
        except Exception:
            raise PublishError(
                "publication deferred; prior valid target preserved where replacement did not complete"
            ) from None
        finally:
            # Cleanup is serialized by the next publication guard. In particular,
            # timeout may have killed the transport after a remote side effect.
            if self.transport is None:
                transport.close()
