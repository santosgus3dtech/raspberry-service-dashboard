from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from raspberry_dashboard import app as dashboard_app
from raspberry_dashboard import network


@pytest.fixture
def sentinel(monkeypatch):
    state = {
        "paths": [],
        "redirect": None,
        "body": json.dumps({
            "network": {"label": "Test network", "cidr": "192.0.2.0/24", "interface": "eth0", "ssids": []},
            "collector": {"last_seen": "2026-09-22T12:00:00Z", "stale": False},
            "counts": {"devices": 3, "online": 1, "offline": 1, "unknown": 1, "open_incidents": 2},
            "diagnosis": [],
            "last_discovery": None,
        }).encode(),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["paths"].append(self.path)
            if state["redirect"]:
                self.send_response(302)
                self.send_header("Location", state["redirect"])
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            self.end_headers()
            if not state["redirect"]:
                self.wfile.write(state["body"])

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    monkeypatch.setattr(network, "PISENTINEL_URL", f"http://127.0.0.1:{server.server_port}/api/summary")
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_network_reads_fixed_backend_and_ignores_query_target(sentinel):
    response = TestClient(dashboard_app.app).get("/api/network?url=http://example.invalid/private")

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["summary"]["counts"] == {
        "devices": 3, "online": 1, "offline": 1, "unknown": 1, "open_incidents": 2,
    }
    assert sentinel["paths"] == ["/api/summary"]


def test_network_preserves_stale_collector_state(sentinel):
    payload = json.loads(sentinel["body"])
    payload["collector"]["stale"] = True
    sentinel["body"] = json.dumps(payload).encode()

    result = network.network_summary()

    assert result["available"] is True
    assert result["summary"]["collector"]["stale"] is True
    assert result["summary"]["counts"]["online"] == 1


@pytest.mark.parametrize("body", [b"not JSON", b"[]", b'{}', b'{"counts": {}}'])
def test_network_rejects_invalid_summary_without_inventing_counts(sentinel, body):
    sentinel["body"] = body

    result = network.network_summary()

    assert result["status"] == "unavailable"
    assert result["available"] is False
    assert "summary" not in result
    assert "counts" not in result


def test_network_does_not_follow_backend_redirects(sentinel):
    sentinel["redirect"] = "/other-destination"

    result = network.network_summary()

    assert result["available"] is False
    assert sentinel["paths"] == ["/api/summary"]


def test_network_timeout_returns_unavailable(monkeypatch):
    class TimeoutOpener:
        def open(self, request, timeout):
            assert timeout == 2
            raise TimeoutError("Private infrastructure detail")

    monkeypatch.setattr(network.urllib.request, "build_opener", lambda *args: TimeoutOpener())

    result = TestClient(dashboard_app.app).get("/api/network").json()

    assert result["available"] is False
    assert result["status"] == "unavailable"
    assert "Private infrastructure detail" not in result["detail"]
    assert "summary" not in result
