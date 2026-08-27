from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from .config import DEMO_MODE, INSTAGRAM_HEALTH_URL
from .demo import demo_inventory, demo_logs, demo_status
from .deploys import list_deploys, run_deploy
from .health import check_http_health, latest_tunnel_url
from .inventory import collect_inventory
from .jobs import dashboard_file, dashboard_meta, list_jobs, update_job
from .logs import service_logs
from .metrics import system_summary
from .notifications import notification_config, send_test_notification
from .services import monitored_service_names, restart_service, service_status
from .ui import HTML


app = FastAPI(title="Raspberry Service Dashboard")


def collect_status() -> dict[str, Any]:
    if DEMO_MODE:
        return demo_status()

    services = [service_status(name) for name in monitored_service_names()]
    instagram_health = check_http_health()
    tunnel_url = latest_tunnel_url()
    system = system_summary()

    return {
        "online": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **system,
        "instagram": {
            "running": instagram_health["ok"]
            and any(
                service["name"] == "instagram-stl-auto-dm" and service["active"]
                for service in services
            ),
            "health_url": INSTAGRAM_HEALTH_URL,
            "health": instagram_health,
        },
        "tunnel": {
            "url": tunnel_url,
            "webhook_url": f"{tunnel_url}/webhook" if tunnel_url else None,
        },
        "services": services,
        "deploys": list_deploys(),
        "notifications": notification_config(),
    }


@app.get("/api/status")
async def api_status() -> dict[str, Any]:
    return collect_status()


@app.get("/api/inventory")
async def api_inventory() -> dict[str, Any]:
    if DEMO_MODE:
        return demo_inventory()
    return collect_inventory()


@app.get("/api/logs/{service_name}")
async def api_logs(service_name: str, limit: int = 120) -> dict[str, Any]:
    if DEMO_MODE:
        return demo_logs(service_name)
    return service_logs(service_name, limit=limit)


@app.post("/api/services/{service_name}/restart")
async def api_restart_service(service_name: str) -> dict[str, Any]:
    if DEMO_MODE:
        return {
            "service": service_name,
            "ok": True,
            "status": demo_status()["services"][0],
            "logs": demo_logs(service_name),
        }
    result = restart_service(service_name)
    result["logs"] = service_logs(service_name, limit=40)
    return result


@app.get("/api/deploys")
async def api_deploys() -> list[dict[str, Any]]:
    if DEMO_MODE:
        return demo_status()["deploys"]
    return list_deploys()


@app.post("/api/deploys/{target_name}/run")
async def api_run_deploy(target_name: str) -> dict[str, Any]:
    if DEMO_MODE:
        return {
            "name": target_name,
            "ok": True,
            "elapsed_ms": 340,
            "command": "git pull --ff-only",
            "return_code": 0,
            "output": "Already up to date.",
            "restart": {"service": target_name, "return_code": 0, "output": ""},
        }
    return run_deploy(target_name)


@app.get("/api/notifications")
async def api_notifications() -> dict[str, Any]:
    if DEMO_MODE:
        return demo_status()["notifications"]
    return notification_config()


@app.post("/api/notifications/test")
async def api_test_notification() -> dict[str, Any]:
    if DEMO_MODE:
        return {"ok": True, "status_code": 200}
    return send_test_notification()


@app.get("/vagas/api/jobs")
async def api_job_applications(request: Request) -> list[dict[str, Any]]:
    return list_jobs(request.query_params)


@app.get("/vagas/api/meta")
async def api_job_application_meta() -> dict[str, Any]:
    return dashboard_meta()


@app.patch("/vagas/api/jobs/{job_id}")
async def api_update_job_application(job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    return update_job(job_id, payload)


@app.get("/vagas", response_class=RedirectResponse)
async def job_applications_redirect() -> RedirectResponse:
    return RedirectResponse(url="/vagas/", status_code=307)


@app.get("/vagas/", response_class=FileResponse)
async def job_applications_dashboard() -> FileResponse:
    return dashboard_file()


@app.get("/vagas/{asset_path:path}", response_class=FileResponse)
async def job_applications_asset(asset_path: str) -> FileResponse:
    return dashboard_file(asset_path)


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> str:
    return HTML
