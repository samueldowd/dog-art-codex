import socket

import pytest


@pytest.fixture(autouse=True)
def deny_network(monkeypatch, request):
    if request.node.get_closest_marker("live") or request.node.get_closest_marker("local_model"):
        pytest.skip("live checks require a separate controlled acceptance runner")

    def denied(*args, **kwargs):
        raise AssertionError("offline test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
