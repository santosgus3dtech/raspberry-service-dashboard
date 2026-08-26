from __future__ import annotations

import subprocess

from fastapi.testclient import TestClient

from raspberry_dashboard import app as dashboard_app


def test_logs_reject_unknown_service():
    client = TestClient(dashboard_app.app)

    response = client.get("/api/logs/ssh")

    assert response.status_code == 404


def test_restart_rejects_unknown_service():
    client = TestClient(dashboard_app.app)

    response = client.post("/api/services/ssh/restart")

    assert response.status_code == 404


def test_restart_uses_sudo_for_allowed_service(monkeypatch):
    calls = []

    def fake_run(command, timeout=2.0):
        calls.append(command)
        if command[:4] == ["sudo", "-n", "systemctl", "restart"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:2] == ["systemctl", "is-active"]:
            return subprocess.CompletedProcess(command, 0, "active\n", "")
        if command[:2] == ["systemctl", "is-enabled"]:
            return subprocess.CompletedProcess(command, 0, "enabled\n", "")
        if command[:2] == ["systemctl", "show"]:
            return subprocess.CompletedProcess(
                command,
                0,
                "ActiveState=active\nSubState=running\nMainPID=123\nNRestarts=0\n",
                "",
            )
        if command and command[0] == "journalctl":
            return subprocess.CompletedProcess(command, 0, "line one\nline two\n", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(dashboard_app, "_run", fake_run)
    client = TestClient(dashboard_app.app)

    response = client.post("/api/services/instagram-stl-auto-dm/restart")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert ["sudo", "-n", "systemctl", "restart", "instagram-stl-auto-dm"] in calls


def test_service_logs_redacts_tokens(monkeypatch):
    def fake_run(command, timeout=2.0):
        return subprocess.CompletedProcess(
            command,
            0,
            (
                "GET /webhook?hub.verify_token=secret-token&access_token=abc123 HTTP/1.1\n"
                "VERIFY_TOKEN=secret-token META_APP_SECRET=secret IG_ACCESS_TOKEN=fake-instagram-token\n"
            ),
            "",
        )

    monkeypatch.setattr(dashboard_app, "_run", fake_run)

    logs = dashboard_app._service_logs("instagram-stl-auto-dm")

    joined = "\n".join(logs["lines"])
    assert "secret-token" not in joined
    assert "abc123" not in joined
    assert "hub.verify_token=<redacted>" in joined

