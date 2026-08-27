from __future__ import annotations

import subprocess

from fastapi.testclient import TestClient

from raspberry_dashboard import app as dashboard_app
from raspberry_dashboard import deploys, jobs, logs, services


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


def test_self_deploy_schedules_delayed_restart(monkeypatch, tmp_path):
    popen_calls = []

    def fake_run(command, cwd=None, capture_output=True, text=True, timeout=120, check=False):
        return subprocess.CompletedProcess(command, 0, "Already up to date.\n", "")

    class FakePopen:
        def __init__(self, command, stdout=None, stderr=None):
            popen_calls.append(command)

    monkeypatch.setattr(deploys, "DEPLOY_ACTIONS_ENABLED", True)
    monkeypatch.setattr(deploys, "DASHBOARD_SERVICE_NAME", "raspberry-status")
    monkeypatch.setattr(
        deploys,
        "deploy_targets",
        lambda: [
            deploys.DeployTarget(
                name="dashboard",
                path=str(tmp_path),
                service="raspberry-status",
                command=["git", "status", "--short"],
            )
        ],
    )
    monkeypatch.setattr(deploys.subprocess, "run", fake_run)
    monkeypatch.setattr(deploys.subprocess, "Popen", FakePopen)
    client = TestClient(dashboard_app.app)

    response = client.post("/api/deploys/dashboard/run")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["restart"]["scheduled"] is True
    assert popen_calls


def test_inventory_endpoint_is_public_safe():
    client = TestClient(dashboard_app.app)

    response = client.get("/api/inventory")

    assert response.status_code == 200
    payload = response.json()
    assert "tools" in payload
    assert "monitored_services" in payload


def create_jobs_db(path):
    import sqlite3

    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE jobs (
          id INTEGER PRIMARY KEY,
          company TEXT,
          title TEXT,
          target_role TEXT,
          location TEXT,
          notes TEXT,
          country TEXT,
          status TEXT,
          work_mode TEXT,
          difficulty TEXT,
          compatibility INTEGER,
          priority TEXT,
          resume_path TEXT,
          resume_version TEXT,
          apply_method TEXT,
          applied_at TEXT,
          updated_at TEXT
        );
        CREATE TABLE application_events (
          id INTEGER PRIMARY KEY,
          job_id INTEGER,
          event_type TEXT,
          status TEXT,
          details TEXT
        );
        INSERT INTO jobs (
          id, company, title, target_role, location, notes, country, status,
          work_mode, difficulty, compatibility, updated_at
        ) VALUES
          (1, 'Avenue Code', 'Python Engineer', 'Backend', 'Brasil', '', 'Brasil', 'Enviada', 'Remoto', 'Facil', 88, CURRENT_TIMESTAMP),
          (2, 'Decskill', 'Application Support', 'Suporte', 'Porto', '', 'Portugal', 'CV adaptado', 'Hibrido', 'Media', 82, CURRENT_TIMESTAMP);
        """
    )
    connection.close()


def test_jobs_dashboard_filters_and_updates(monkeypatch, tmp_path):
    db_path = tmp_path / "candidaturas.db"
    create_jobs_db(db_path)
    monkeypatch.setattr(jobs, "JOBS_DB_PATH", db_path)
    client = TestClient(dashboard_app.app)

    listed = client.get("/vagas/api/jobs?country=Brasil&min_compatibility=80")
    updated = client.patch(
        "/vagas/api/jobs/2",
        json={"status": "Enviada", "notes": "Enviada pelo painel"},
    )
    meta = client.get("/vagas/api/meta")

    assert listed.status_code == 200
    assert [item["company"] for item in listed.json()] == ["Avenue Code"]
    assert updated.status_code == 200
    assert updated.json()["status"] == "Enviada"
    assert meta.json()["summary"]["sent"] == 2


def test_jobs_dashboard_serves_spa(monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>Candidaturas</h1>", encoding="utf-8")
    monkeypatch.setattr(jobs, "JOBS_DIST_DIR", dist)
    client = TestClient(dashboard_app.app)

    redirect = client.get("/vagas", follow_redirects=False)
    page = client.get("/vagas/")
    fallback = client.get("/vagas/qualquer-rota")

    assert redirect.status_code == 307
    assert redirect.headers["location"] == "/vagas/"
    assert page.status_code == 200
    assert "Candidaturas" in page.text
    assert fallback.status_code == 200
