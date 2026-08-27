from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from .command import run
from .config import INSTAGRAM_HEALTH_URL


def check_http_health(url: str = INSTAGRAM_HEALTH_URL) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
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


def latest_tunnel_url(service_name: str = "instagram-stl-auto-dm-tunnel") -> str | None:
    command = [
        "journalctl",
        "-u",
        service_name,
        "--no-pager",
        "-n",
        "200",
    ]
    result = run(command)
    if result.returncode != 0:
        result = run(["sudo", "-n", *command])

    urls = re.findall(
        r"https://[-a-zA-Z0-9.]+\.trycloudflare\.com",
        result.stdout + result.stderr,
    )
    return urls[-1] if urls else None
