from __future__ import annotations

import subprocess

from fastapi.testclient import TestClient

from raspberry_dashboard import app as dashboard_app
from raspberry_dashboard import deploys, logs, services


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

    monkeypatch.setattr(services, "run", fake_run)
    monkeypatch.setattr(logs, "run", fake_run)
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

    monkeypatch.setattr(logs, "run", fake_run)

    payload = logs.service_logs("instagram-stl-auto-dm")

    joined = "\n".join(payload["lines"])
    assert "secret-token" not in joined
    assert "abc123" not in joined
    assert "hub.verify_token=<redacted>" in joined


def test_deploy_actions_disabled_by_default(monkeypatch, tmp_path):
    target_json = (
        "[{"
        f'"name":"demo","path":"{tmp_path.as_posix()}","service":"demo.service"'
        "}]"
    )
    monkeypatch.setenv("DEPLOY_TARGETS_JSON", target_json)
    monkeypatch.setattr(deploys, "DEPLOY_ACTIONS_ENABLED", False)
    client = TestClient(dashboard_app.app)

    listed = client.get("/api/deploys")
    response = client.post("/api/deploys/demo/run")

    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "demo"
    assert listed.json()[0]["actions_enabled"] is False
    assert response.status_code == 403


def test_inventory_endpoint_is_public_safe():
    client = TestClient(dashboard_app.app)

    response = client.get("/api/inventory")

    assert response.status_code == 200
    payload = response.json()
    assert "tools" in payload
    assert "monitored_services" in payload
