from __future__ import annotations

import os
import platform
import shutil
import socket
import time
from pathlib import Path
from typing import Any

from .config import HOST_PROC, HOST_ROOT, HOST_SYS


APP_STARTED_AT = time.time()


def read_uptime() -> dict[str, Any]:
    uptime_path = Path(HOST_PROC) / "uptime"
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


def read_memory() -> dict[str, Any]:
    meminfo = Path(HOST_PROC) / "meminfo"
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


def read_temperature() -> float | None:
    for path in (
        Path(HOST_SYS) / "class/thermal/thermal_zone0/temp",
        Path(HOST_SYS) / "class/hwmon/hwmon0/temp1_input",
    ):
        if path.exists():
            raw = path.read_text(encoding="utf-8").strip()
            if raw.lstrip("-").isdigit():
                return round(int(raw) / 1000, 1)
    return None


def read_disk() -> dict[str, Any]:
    usage = shutil.disk_usage(HOST_ROOT)
    used_percent = round((usage.used / usage.total) * 100, 1)
    return {
        "total_gb": round(usage.total / (1024**3), 1),
        "free_gb": round(usage.free / (1024**3), 1),
        "used_percent": used_percent,
    }


def load_average() -> list[float] | None:
    try:
        return [round(value, 2) for value in os.getloadavg()]
    except (AttributeError, OSError):
        return None


def system_summary() -> dict[str, Any]:
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "uptime": read_uptime(),
        "load_average": load_average(),
        "memory": read_memory(),
        "disk": read_disk(),
        "temperature_c": read_temperature(),
        "monitor": {
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(APP_STARTED_AT)),
        },
    }
