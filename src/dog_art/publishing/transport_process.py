"""Killable SMB worker: no server response can hold rollover indefinitely."""

import multiprocessing
import time


class TransportTimeout(TimeoutError):
    pass


def _worker(connection, settings, factory):
    adapter = None
    try:
        if factory is None:
            from . import SMBTransport

            adapter = SMBTransport(settings)
        else:
            adapter = factory(settings)
        connection.send(("ok", None))
        while True:
            method, args = connection.recv()
            if method == "close":
                return
            if method not in ("read", "write_new", "replace", "remove_owned_temp"):
                raise ValueError("unsupported operation")
            try:
                connection.send(("ok", getattr(adapter, method)(*args)))
            except FileNotFoundError:
                connection.send(("missing", None))
            except Exception:
                connection.send(("error", None))
    except (EOFError, BrokenPipeError):
        pass
    except Exception:
        try:
            connection.send(("error", None))
        except (EOFError, BrokenPipeError, OSError):
            pass
    finally:
        if adapter:
            try:
                adapter.close()
            except Exception:
                pass
        connection.close()


class BoundedSMBTransport:
    """One strict total deadline includes connect, upload, replace, readback and cleanup.

    Secrets travel over a private multiprocessing channel, never argv/environment.
    The parent owns the publication lock. Spawn gives the SMB worker no lock FD;
    termination on timeout releases parent control and permits immediate rollover.
    A timed-out replace may have succeeded: next attempt reconciles remote hash.
    """

    def __init__(self, settings, *, timeout=25, factory=None):
        self.deadline = time.monotonic() + timeout
        ctx = multiprocessing.get_context("spawn")
        self.connection, child = ctx.Pipe()
        self.process = ctx.Process(target=_worker, args=(child, settings, factory), daemon=True)
        self.process.start()
        child.close()
        self.closed = False
        try:
            self._receive()
        except BaseException:
            self.close(force=True)
            raise

    def _receive(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0 or not self.connection.poll(remaining):
            self.close(force=True)
            raise TransportTimeout("SMB total deadline exceeded; reconcile next attempt")
        try:
            state, result = self.connection.recv()
        except (EOFError, OSError):
            self.close(force=True)
            raise TransportTimeout("SMB worker unavailable") from None
        if state == "missing":
            raise FileNotFoundError("owned remote image missing")
        if state != "ok":
            raise OSError("SMB operation deferred")
        return result

    def _call(self, method, *args):
        if self.closed:
            raise TransportTimeout("SMB worker already stopped")
        if time.monotonic() >= self.deadline:
            self.close(force=True)
            raise TransportTimeout("SMB total deadline exceeded")
        self.connection.send((method, args))
        return self._receive()

    def read(self, path):
        return self._call("read", path)

    def write_new(self, path, data):
        return self._call("write_new", path, data)

    def replace(self, source, target):
        return self._call("replace", source, target)

    def remove_owned_temp(self, path):
        return self._call("remove_owned_temp", path)

    def close(self, *, force=False):
        if self.closed:
            return
        self.closed = True
        if not force:
            try:
                self.connection.send(("close", ()))
            except (EOFError, BrokenPipeError, OSError):
                pass
            self.process.join(timeout=0.2)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=1)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=1)
        self.connection.close()
