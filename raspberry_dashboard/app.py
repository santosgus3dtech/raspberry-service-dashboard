from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse


APP_STARTED_AT = time.time()
DEFAULT_SERVICES = "instagram-stl-auto-dm,instagram-stl-auto-dm-tunnel"
ACTIONABLE_SERVICES = {
    item.strip()
    for item in os.getenv("RESTARTABLE_SERVICES", DEFAULT_SERVICES).split(",")
    if item.strip()
}
INSTAGRAM_HEALTH_URL = os.getenv(
    "INSTAGRAM_HEALTH_URL",
    "http://127.0.0.1:8000/health",
)
REDACTION_PATTERNS = (
    (
        re.compile(r"((?:hub\.verify_token|hub_verify_token|access_token)=)[^&\s\"]+"),
        r"\1<redacted>",
    ),
    (
        re.compile(r"((?:VERIFY_TOKEN|META_APP_SECRET|IG_ACCESS_TOKEN)=)\S+"),
        r"\1<redacted>",
    ),
    (
        re.compile(r"(Authorization:\s*Bearer\s+)\S+", re.IGNORECASE),
        r"\1<redacted>",
    ),
    (
        re.compile(r"\bIGAA[A-Za-z0-9_-]{20,}\b"),
        "<redacted-instagram-token>",
    ),
)

app = FastAPI(title="Raspberry Service Dashboard")


def _run(command: list[str], timeout: float = 2.0) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(command, 127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(command, 124, exc.stdout or "", exc.stderr or str(exc))


def _monitored_service_names() -> list[str]:
    return [
        item.strip()
        for item in os.getenv("MONITORED_SERVICES", DEFAULT_SERVICES).split(",")
        if item.strip()
    ]


def _assert_known_service(name: str) -> None:
    if name not in set(_monitored_service_names()) | ACTIONABLE_SERVICES:
        raise HTTPException(status_code=404, detail="Unknown service.")


def _assert_actionable_service(name: str) -> None:
    if name not in ACTIONABLE_SERVICES:
        raise HTTPException(status_code=403, detail="Restart is not allowed for this service.")


def _parse_key_values(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def _redact_log_line(line: str) -> str:
    redacted = line
    for pattern, replacement in REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _service_status(name: str) -> dict[str, Any]:
    active = _run(["systemctl", "is-active", name])
    enabled = _run(["systemctl", "is-enabled", name])
    show = _run(
        [
            "systemctl",
            "show",
            name,
            "--property=LoadState,ActiveState,SubState,UnitFileState,MainPID,ActiveEnterTimestamp,NRestarts",
        ],
    )
    props = _parse_key_values(show.stdout)

    active_state = (active.stdout or props.get("ActiveState", "")).strip()
    enabled_state = (enabled.stdout or props.get("UnitFileState", "")).strip()

    return {
        "name": name,
        "active": active_state == "active",
        "active_state": active_state or "unknown",
        "enabled_state": enabled_state or "unknown",
        "sub_state": props.get("SubState", "unknown"),
        "main_pid": props.get("MainPID", "0"),
        "started_at": props.get("ActiveEnterTimestamp", ""),
        "restarts": props.get("NRestarts", "0"),
    }


def _read_uptime() -> dict[str, Any]:
    uptime_path = Path("/proc/uptime")
    if not uptime_path.exists():
        seconds = time.time() - APP_STARTED_AT
    else:
        seconds = float(uptime_path.read_text(encoding="utf-8").split()[0])

    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    return {
        "seconds": round(seconds),
        "human": f"{days}d {hours}h {minutes}m",
    }


def _read_memory() -> dict[str, Any]:
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return {"total_mb": None, "available_mb": None, "used_percent": None}

    data: dict[str, int] = {}
    for line in meminfo.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition(":")
        number = value.strip().split()[0]
        if number.isdigit():
            data[key] = int(number)

    total_kb = data.get("MemTotal", 0)
    available_kb = data.get("MemAvailable", 0)
    used_percent = 0
    if total_kb:
        used_percent = round(((total_kb - available_kb) / total_kb) * 100, 1)

    return {
        "total_mb": round(total_kb / 1024),
        "available_mb": round(available_kb / 1024),
        "used_percent": used_percent,
    }


def _read_temperature() -> float | None:
    for path in (
        Path("/sys/class/thermal/thermal_zone0/temp"),
        Path("/sys/class/hwmon/hwmon0/temp1_input"),
    ):
        if path.exists():
            raw = path.read_text(encoding="utf-8").strip()
            if raw.lstrip("-").isdigit():
                return round(int(raw) / 1000, 1)
    return None


def _read_disk() -> dict[str, Any]:
    usage = shutil.disk_usage("/")
    used_percent = round((usage.used / usage.total) * 100, 1)
    return {
        "total_gb": round(usage.total / (1024**3), 1),
        "free_gb": round(usage.free / (1024**3), 1),
        "used_percent": used_percent,
    }


def _check_instagram_health() -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(INSTAGRAM_HEALTH_URL, timeout=2) as response:
            body = response.read().decode("utf-8")
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = {"raw": body[:200]}
            return {
                "ok": 200 <= response.status < 300,
                "status_code": response.status,
                "latency_ms": elapsed_ms,
                "payload": payload,
            }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "status_code": None,
            "latency_ms": elapsed_ms,
            "error": str(exc),
        }


def _latest_tunnel_url() -> str | None:
    command = [
        "journalctl",
        "-u",
        "instagram-stl-auto-dm-tunnel",
        "--no-pager",
        "-n",
        "200",
    ]
    result = _run(command)
    if result.returncode != 0:
        result = _run(["sudo", "-n", *command])

    urls = re.findall(
        r"https://[-a-zA-Z0-9.]+\.trycloudflare\.com",
        result.stdout + result.stderr,
    )
    return urls[-1] if urls else None


def _service_logs(name: str, limit: int = 120) -> dict[str, Any]:
    _assert_known_service(name)
    safe_limit = max(20, min(limit, 400))
    command = [
        "journalctl",
        "-u",
        name,
        "--no-pager",
        "-n",
        str(safe_limit),
        "-o",
        "short-iso",
    ]
    result = _run(command, timeout=5)
    if result.returncode != 0:
        result = _run(["sudo", "-n", *command], timeout=5)

    output = (result.stdout or result.stderr or "").strip()
    raw_lines = output.splitlines()[-safe_limit:] if output else []
    lines = [_redact_log_line(line) for line in raw_lines]
    return {
        "service": name,
        "ok": result.returncode == 0,
        "return_code": result.returncode,
        "lines": lines,
    }


def _restart_service(name: str) -> dict[str, Any]:
    _assert_known_service(name)
    _assert_actionable_service(name)

    result = _run(["sudo", "-n", "systemctl", "restart", name], timeout=20)
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=(result.stderr or result.stdout or "Failed to restart service.").strip(),
        )

    time.sleep(1)
    return {
        "service": name,
        "ok": True,
        "status": _service_status(name),
        "logs": _service_logs(name, limit=40),
    }


def _load_average() -> list[float] | None:
    try:
        return [round(value, 2) for value in os.getloadavg()]
    except (AttributeError, OSError):
        return None


def collect_status() -> dict[str, Any]:
    service_names = _monitored_service_names()
    services = [_service_status(name) for name in service_names]
    instagram_health = _check_instagram_health()
    tunnel_url = _latest_tunnel_url()

    return {
        "online": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "uptime": _read_uptime(),
        "load_average": _load_average(),
        "memory": _read_memory(),
        "disk": _read_disk(),
        "temperature_c": _read_temperature(),
        "monitor": {
            "started_at": datetime.fromtimestamp(
                APP_STARTED_AT,
                timezone.utc,
            ).isoformat(),
        },
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
    }


@app.get("/api/status")
async def api_status() -> dict[str, Any]:
    return collect_status()


@app.get("/api/logs/{service_name}")
async def api_logs(service_name: str, limit: int = 120) -> dict[str, Any]:
    return _service_logs(service_name, limit=limit)


@app.post("/api/services/{service_name}/restart")
async def api_restart_service(service_name: str) -> dict[str, Any]:
    return _restart_service(service_name)


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> str:
    return HTML


HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Raspberry Service Dashboard</title>
  <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%23fff7df'/%3E%3Cpath d='M31 17c1-8 8-11 16-9-1 7-6 12-14 12z' fill='%23178a4a'/%3E%3Cpath d='M29 17c-5-6-12-6-18-2 4 6 10 8 17 5z' fill='%230f5e38'/%3E%3Ccircle cx='22' cy='31' r='10' fill='%23c51f46'/%3E%3Ccircle cx='34' cy='31' r='10' fill='%23c51f46'/%3E%3Ccircle cx='28' cy='43' r='11' fill='%23c51f46'/%3E%3Ccircle cx='22' cy='31' r='4' fill='%23ec5b75'/%3E%3Ccircle cx='34' cy='31' r='4' fill='%23ec5b75'/%3E%3Ccircle cx='28' cy='43' r='4' fill='%23ec5b75'/%3E%3Cpath d='M16 31c0-10 7-17 16-17s16 7 16 17c0 13-8 23-20 23S16 44 16 31z' fill='none' stroke='%237b1130' stroke-width='4' stroke-linejoin='round'/%3E%3C/svg%3E">
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8f3;
      --ink: #1a1918;
      --muted: #657166;
      --panel: #fffdf8;
      --panel-soft: #f0f5e8;
      --line: #d9dfcf;
      --raspberry: #c51f46;
      --raspberry-dark: #7b1130;
      --leaf: #178a4a;
      --leaf-dark: #0f5e38;
      --cream: #fff7df;
      --terminal: #101511;
      --terminal-line: #243527;
      --terminal-text: #d7f7d5;
      --ok: #16884f;
      --warn: #b36b00;
      --bad: #bf2641;
      --shadow: 0 14px 36px rgba(61, 35, 30, 0.12);
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      background:
        linear-gradient(180deg, rgba(197, 31, 70, 0.10), rgba(23, 138, 74, 0.08) 42%, transparent 100%),
        var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }

    button {
      font: inherit;
    }

    .shell {
      width: min(1220px, calc(100% - 32px));
      margin: 0 auto;
      padding: 26px 0 34px;
    }

    .hero {
      position: relative;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 20px;
      align-items: center;
      min-height: 168px;
      padding: 24px;
      border: 1px solid rgba(123, 17, 48, 0.18);
      border-radius: 8px;
      background:
        linear-gradient(135deg, rgba(255, 253, 248, 0.95), rgba(255, 247, 223, 0.92)),
        var(--panel);
      box-shadow: var(--shadow);
      overflow: hidden;
    }

    .hero::before {
      content: "";
      position: absolute;
      inset: 0;
      background-image:
        linear-gradient(rgba(23, 138, 74, 0.08) 1px, transparent 1px),
        linear-gradient(90deg, rgba(23, 138, 74, 0.08) 1px, transparent 1px);
      background-size: 24px 24px;
      pointer-events: none;
    }

    .hero-content,
    .hero-side {
      position: relative;
      z-index: 1;
    }

    .brand-row {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 14px;
    }

    .berry-mark {
      position: relative;
      width: 44px;
      height: 44px;
      flex: 0 0 auto;
    }

    .berry-mark::before,
    .berry-mark::after {
      content: "";
      position: absolute;
    }

    .berry-mark::before {
      left: 15px;
      top: 0;
      width: 15px;
      height: 19px;
      border-radius: 14px 14px 2px 14px;
      background: var(--leaf);
      transform: rotate(36deg);
      box-shadow: -8px 4px 0 var(--leaf-dark);
    }

    .berry-mark::after {
      left: 4px;
      bottom: 0;
      width: 36px;
      height: 30px;
      border-radius: 18px 18px 20px 20px;
      background:
        radial-gradient(circle at 10px 10px, #ec5b75 0 5px, transparent 6px),
        radial-gradient(circle at 24px 10px, #ec5b75 0 5px, transparent 6px),
        radial-gradient(circle at 17px 21px, #ec5b75 0 5px, transparent 6px),
        var(--raspberry);
      border: 2px solid var(--raspberry-dark);
    }

    h1 {
      margin: 0;
      font-size: 32px;
      line-height: 1.08;
      font-weight: 820;
    }

    .subtitle {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }

    .hero-copy {
      width: min(680px, 100%);
      margin: 0;
      color: #3d473e;
      font-size: 15px;
      line-height: 1.55;
    }

    .hero-side {
      display: grid;
      gap: 10px;
      min-width: 260px;
    }

    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 36px;
      padding: 8px 12px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--panel);
      color: var(--ink);
      font-size: 13px;
      font-weight: 750;
      white-space: nowrap;
    }

    .dot {
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: var(--muted);
      box-shadow: 0 0 0 3px rgba(101, 113, 102, 0.12);
    }

    .ok .dot,
    .dot.ok {
      background: var(--ok);
      box-shadow: 0 0 0 3px rgba(22, 136, 79, 0.15);
    }

    .bad .dot,
    .dot.bad {
      background: var(--bad);
      box-shadow: 0 0 0 3px rgba(191, 38, 65, 0.15);
    }

    .warn .dot,
    .dot.warn {
      background: var(--warn);
      box-shadow: 0 0 0 3px rgba(179, 107, 0, 0.16);
    }

    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin: 18px 0 12px;
    }

    .toolbar-title {
      margin: 0;
      font-size: 18px;
      line-height: 1.2;
    }

    .button-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }

    .btn {
      min-height: 36px;
      padding: 8px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--ink);
      cursor: pointer;
      font-size: 13px;
      font-weight: 760;
      transition: transform 150ms ease, border-color 150ms ease, background 150ms ease;
    }

    .btn:hover {
      transform: translateY(-1px);
      border-color: rgba(197, 31, 70, 0.42);
    }

    .btn:disabled {
      cursor: wait;
      opacity: 0.56;
      transform: none;
    }

    .btn.primary {
      border-color: var(--raspberry-dark);
      background: var(--raspberry);
      color: #fff;
    }

    .btn.leaf {
      border-color: var(--leaf-dark);
      background: var(--leaf);
      color: #fff;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 12px;
    }

    .metric,
    .section {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 253, 248, 0.96);
      box-shadow: 0 6px 18px rgba(61, 35, 30, 0.06);
    }

    .metric {
      position: relative;
      min-height: 122px;
      padding: 16px;
      overflow: hidden;
    }

    .metric::after {
      content: "";
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      height: 4px;
      background: linear-gradient(90deg, var(--raspberry), var(--leaf));
      opacity: 0.85;
    }

    .label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 780;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .value {
      margin-top: 12px;
      font-size: 26px;
      line-height: 1.12;
      font-weight: 840;
      overflow-wrap: anywhere;
    }

    .hint {
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
    }

    .section {
      margin-top: 12px;
      padding: 18px;
    }

    .section-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }

    .section h2 {
      margin: 0;
      font-size: 18px;
      line-height: 1.2;
    }

    .services {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .service-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
      min-height: 112px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background:
        linear-gradient(180deg, rgba(240, 245, 232, 0.95), rgba(255, 253, 248, 0.96));
    }

    .service-name {
      font-weight: 820;
      overflow-wrap: anywhere;
    }

    .service-meta {
      margin-top: 6px;
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }

    .service-actions {
      display: flex;
      flex-direction: column;
      gap: 8px;
      align-items: stretch;
      min-width: 118px;
    }

    .webhook-box {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
    }

    code {
      display: block;
      min-height: 48px;
      padding: 14px;
      border-radius: 8px;
      border: 1px solid var(--terminal-line);
      background: var(--terminal);
      color: var(--terminal-text);
      overflow-x: auto;
      white-space: nowrap;
      font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
      font-size: 13px;
    }

    .console-wrap {
      border: 1px solid var(--terminal-line);
      border-radius: 8px;
      overflow: hidden;
      background: var(--terminal);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
    }

    .console-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 12px;
      border-bottom: 1px solid var(--terminal-line);
      background: #182019;
      color: #edf7e7;
    }

    .console-title {
      font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
      font-size: 13px;
      font-weight: 760;
      overflow-wrap: anywhere;
    }

    .console-tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .tab {
      min-height: 32px;
      padding: 7px 10px;
      border: 1px solid #344539;
      border-radius: 8px;
      background: #101511;
      color: #bedabe;
      cursor: pointer;
      font-size: 12px;
      font-weight: 760;
    }

    .tab.active {
      border-color: #7dde96;
      color: #f1fff1;
      background: #1c2d20;
    }

    .console {
      height: 340px;
      margin: 0;
      padding: 14px;
      overflow: auto;
      color: var(--terminal-text);
      font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      line-height: 1.55;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    .footer {
      margin-top: 14px;
      color: var(--muted);
      font-size: 13px;
    }

    .toast {
      position: fixed;
      right: 16px;
      bottom: 16px;
      z-index: 10;
      max-width: min(420px, calc(100% - 32px));
      min-height: 44px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--ink);
      box-shadow: var(--shadow);
      font-size: 13px;
      opacity: 0;
      transform: translateY(12px);
      pointer-events: none;
      transition: opacity 180ms ease, transform 180ms ease;
    }

    .toast.show {
      opacity: 1;
      transform: translateY(0);
    }

    @media (max-width: 900px) {
      .hero {
        grid-template-columns: 1fr;
      }

      .hero-side {
        min-width: 0;
      }

      .grid,
      .services {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .toolbar,
      .section-head {
        align-items: flex-start;
        flex-direction: column;
      }
    }

    @media (max-width: 620px) {
      .shell {
        width: min(100% - 20px, 1220px);
        padding-top: 14px;
      }

      .hero {
        padding: 18px;
      }

      .grid,
      .services {
        grid-template-columns: 1fr;
      }

      .service-row,
      .webhook-box {
        grid-template-columns: 1fr;
      }

      .service-actions {
        min-width: 0;
        flex-direction: row;
        flex-wrap: wrap;
      }

      h1 {
        font-size: 26px;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="hero-content">
        <div class="brand-row">
          <div class="berry-mark" aria-hidden="true"></div>
          <div>
            <h1>Raspberry Service Dashboard</h1>
            <div class="subtitle" id="subtitle">Carregando dados...</div>
          </div>
        </div>
        <p class="hero-copy" id="hero-copy">Monitorando servicos no Raspberry com status, logs e acoes seguras.</p>
      </div>
      <div class="hero-side">
        <div class="pill" id="main-status"><span class="dot"></span><span>Carregando</span></div>
        <div class="pill" id="health-pill"><span class="dot"></span><span>Health check pendente</span></div>
        <div class="pill" id="tunnel-pill"><span class="dot"></span><span>Tunnel pendente</span></div>
      </div>
    </section>

    <div class="toolbar">
      <h2 class="toolbar-title">Sistema</h2>
      <div class="button-row">
        <button class="btn leaf" id="refresh-btn" type="button">Atualizar</button>
      </div>
    </div>

    <section class="grid" aria-label="Metricas do Raspberry">
      <div class="metric"><div class="label">Uptime</div><div class="value" id="uptime">--</div><div class="hint" id="host">--</div></div>
      <div class="metric"><div class="label">Memoria usada</div><div class="value" id="memory">--</div><div class="hint" id="memory-detail">--</div></div>
      <div class="metric"><div class="label">Disco usado</div><div class="value" id="disk">--</div><div class="hint" id="disk-detail">--</div></div>
      <div class="metric"><div class="label">Temperatura</div><div class="value" id="temperature">--</div><div class="hint" id="load">--</div></div>
      <div class="metric"><div class="label">DMs enviadas</div><div class="value" id="messages-sent">--</div><div class="hint" id="messages-detail">--</div></div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Servicos monitorados</h2>
        <div class="button-row">
          <button class="btn" type="button" data-log-service="instagram-stl-auto-dm">Logs backend</button>
          <button class="btn" type="button" data-log-service="instagram-stl-auto-dm-tunnel">Logs tunnel</button>
        </div>
      </div>
      <div class="services" id="services"></div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Webhook publico</h2>
      </div>
      <div class="webhook-box">
        <code id="webhook">--</code>
        <button class="btn primary" id="copy-webhook" type="button">Copiar</button>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Console</h2>
        <div class="button-row">
          <button class="btn leaf" id="refresh-logs" type="button">Atualizar logs</button>
        </div>
      </div>
      <div class="console-wrap">
        <div class="console-head">
          <div class="console-title" id="console-title">journalctl</div>
          <div class="console-tabs" id="console-tabs"></div>
        </div>
        <pre class="console" id="console">Carregando logs...</pre>
      </div>
    </section>

    <div class="footer" id="footer">Atualiza automaticamente a cada 5 segundos.</div>
  </main>

  <div class="toast" id="toast"></div>

  <script>
    const $ = (id) => document.getElementById(id);
    const actionableServices = new Set(["instagram-stl-auto-dm", "instagram-stl-auto-dm-tunnel"]);
    let selectedLogService = "instagram-stl-auto-dm";
    let lastStatus = null;

    function showToast(message) {
      const toast = $("toast");
      toast.textContent = message;
      toast.classList.add("show");
      window.clearTimeout(showToast.timer);
      showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 3200);
    }

    function statePill(active, label, warn = false) {
      const cls = active ? "ok" : warn ? "warn" : "bad";
      return `<span class="pill ${cls}"><span class="dot"></span><span>${label}</span></span>`;
    }

    function compactServiceName(name) {
      return name.replace("instagram-stl-auto-dm", "auto-dm");
    }

    function setStatusPill(id, active, text, warn = false) {
      const node = $(id);
      node.className = `pill ${active ? "ok" : warn ? "warn" : "bad"}`;
      node.innerHTML = `<span class="dot"></span><span>${text}</span>`;
    }

    function numberText(value) {
      const number = Number(value);
      return Number.isFinite(number) ? number.toLocaleString("pt-BR") : "--";
    }

    function serviceMarkup(service) {
      const state = service.active ? "Ativo" : "Parado";
      const restart = actionableServices.has(service.name)
        ? `<button class="btn primary" type="button" data-restart-service="${service.name}">Reiniciar</button>`
        : "";
      return `
        <div class="service-row">
          <div>
            <div class="service-name">${service.name}</div>
            <div class="service-meta">state=${service.active_state} sub=${service.sub_state} pid=${service.main_pid} restarts=${service.restarts}</div>
            <div class="service-meta">start=${service.started_at || "--"}</div>
          </div>
          <div class="service-actions">
            ${statePill(service.active, state)}
            <button class="btn" type="button" data-log-service="${service.name}">Logs</button>
            ${restart}
          </div>
        </div>
      `;
    }

    function renderLogTabs(services) {
      $("console-tabs").innerHTML = (services || []).map((service) => {
        const active = service.name === selectedLogService ? " active" : "";
        return `<button class="tab${active}" type="button" data-log-service="${service.name}">${compactServiceName(service.name)}</button>`;
      }).join("");
    }

    async function refresh() {
      try {
        const response = await fetch("/api/status", { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        lastStatus = data;
        const instagramOk = Boolean(data.instagram && data.instagram.running);
        const tunnelOk = Boolean(data.tunnel && data.tunnel.webhook_url);
        const latency = data.instagram?.health?.latency_ms;
        const instagramPayload = data.instagram?.health?.payload || {};

        setStatusPill("main-status", instagramOk, instagramOk ? "Instagram online" : "Instagram com alerta");
        setStatusPill("health-pill", Boolean(data.instagram?.health?.ok), latency == null ? "Health check" : `Health ${latency} ms`);
        setStatusPill("tunnel-pill", tunnelOk, tunnelOk ? "Tunnel publicado" : "Tunnel sem URL", !tunnelOk);

        $("subtitle").textContent = `${data.hostname} - ${new Date(data.timestamp).toLocaleString()}`;
        $("hero-copy").textContent = data.platform || "Monitorando o Raspberry e o backend do Instagram Auto DM.";
        $("uptime").textContent = data.uptime?.human || "--";
        $("host").textContent = data.hostname || "--";
        $("memory").textContent = data.memory?.used_percent == null ? "--" : `${data.memory.used_percent}%`;
        $("memory-detail").textContent = data.memory?.available_mb == null ? "--" : `${data.memory.available_mb} MB livres de ${data.memory.total_mb} MB`;
        $("disk").textContent = data.disk?.used_percent == null ? "--" : `${data.disk.used_percent}%`;
        $("disk-detail").textContent = data.disk?.free_gb == null ? "--" : `${data.disk.free_gb} GB livres de ${data.disk.total_gb} GB`;
        $("temperature").textContent = data.temperature_c == null ? "--" : `${data.temperature_c} C`;
        $("load").textContent = data.load_average ? `load ${data.load_average.join(" / ")}` : "--";
        $("messages-sent").textContent = numberText(instagramPayload.messages_sent);
        $("messages-detail").textContent = `vistos ${numberText(instagramPayload.comments_seen)} · falhas ${numberText(instagramPayload.delivery_failures)}`;
        $("services").innerHTML = (data.services || []).map(serviceMarkup).join("");
        renderLogTabs(data.services || []);
        $("webhook").textContent = data.tunnel?.webhook_url || "Tunnel URL nao encontrada nos logs";
        $("footer").textContent = `Ultima leitura: ${new Date(data.timestamp).toLocaleTimeString()}. Auto-refresh ativo.`;
      } catch (error) {
        setStatusPill("main-status", false, "Painel offline");
        $("subtitle").textContent = `Falha ao buscar status: ${error.message}`;
      }
    }

    async function loadLogs(service = selectedLogService) {
      selectedLogService = service;
      $("console-title").textContent = `journalctl -u ${service}`;
      $("console").textContent = "Carregando logs...";
      if (lastStatus) renderLogTabs(lastStatus.services || []);
      try {
        const response = await fetch(`/api/logs/${encodeURIComponent(service)}?limit=160`, { cache: "no-store" });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.detail || `HTTP ${response.status}`);
        $("console").textContent = data.lines.length ? data.lines.join("\\n") : "Sem logs para exibir.";
        $("console").scrollTop = $("console").scrollHeight;
      } catch (error) {
        $("console").textContent = `Falha ao carregar logs: ${error.message}`;
      }
    }

    async function restartService(service, button) {
      if (!actionableServices.has(service)) return;
      const confirmed = window.confirm(`Reiniciar ${service}?`);
      if (!confirmed) return;

      button.disabled = true;
      button.textContent = "Reiniciando";
      try {
        const response = await fetch(`/api/services/${encodeURIComponent(service)}/restart`, { method: "POST" });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.detail || `HTTP ${response.status}`);
        showToast(`${service} reiniciado`);
        await refresh();
        await loadLogs(service);
      } catch (error) {
        showToast(`Falha ao reiniciar: ${error.message}`);
      } finally {
        button.disabled = false;
        button.textContent = "Reiniciar";
      }
    }

    document.addEventListener("click", (event) => {
      const logButton = event.target.closest("[data-log-service]");
      if (logButton) {
        loadLogs(logButton.dataset.logService);
        return;
      }

      const restartButton = event.target.closest("[data-restart-service]");
      if (restartButton) {
        restartService(restartButton.dataset.restartService, restartButton);
      }
    });

    $("refresh-btn").addEventListener("click", refresh);
    $("refresh-logs").addEventListener("click", () => loadLogs(selectedLogService));
    $("copy-webhook").addEventListener("click", async () => {
      const value = $("webhook").textContent.trim();
      try {
        await navigator.clipboard.writeText(value);
        showToast("Webhook copiado");
      } catch {
        showToast(value);
      }
    });

    refresh().then(() => loadLogs(selectedLogService));
    setInterval(refresh, 5000);
    setInterval(() => loadLogs(selectedLogService), 10000);
  </script>
</body>
</html>
"""
