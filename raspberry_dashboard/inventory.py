from __future__ import annotations

import os
import shutil
import socket
from pathlib import Path
from typing import Any

from .command import run
from .config import HOST_PROC, HOST_ROOT, HOST_SYS, INVENTORY_EXTRA_LABEL, MONITORED_SERVICES


def _read_model() -> str | None:
    for path in (Path("/proc/device-tree/model"), Path("/sys/firmware/devicetree/base/model")):
        host_path = Path(str(path).replace("/proc", HOST_PROC, 1).replace("/sys", HOST_SYS, 1))
        if host_path.exists():
            return host_path.read_text(encoding="utf-8", errors="ignore").strip("\x00\n ")
    return None


def _ip_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        host = socket.gethostname()
        for result in socket.getaddrinfo(host, None):
            address = result[4][0]
            if ":" not in address and not address.startswith("127."):
                addresses.add(address)
    except OSError:
        pass
    return sorted(addresses)


def _command_version(command: str, version_args: list[str] | None = None) -> dict[str, Any]:
    path = shutil.which(command)
    if not path:
        return {"installed": False, "path": None, "version": None}

    args = version_args or ["--version"]
    result = run([command, *args], timeout=3)
    version = (result.stdout or result.stderr).splitlines()
    return {
        "installed": True,
        "path": path,
        "version": version[0] if version else "",
    }


def _mounts() -> list[dict[str, Any]]:
    mounts: list[dict[str, Any]] = []
    for mount in (HOST_ROOT, "/boot", "/boot/firmware"):
        try:
            usage = shutil.disk_usage(mount)
        except OSError:
            continue
        mounts.append(
            {
                "mount": mount,
                "total_gb": round(usage.total / (1024**3), 1),
                "free_gb": round(usage.free / (1024**3), 1),
                "used_percent": round((usage.used / usage.total) * 100, 1),
            }
        )
    return mounts


def collect_inventory() -> dict[str, Any]:
    return {
        "label": INVENTORY_EXTRA_LABEL,
        "model": _read_model(),
        "ip_addresses": _ip_addresses(),
        "monitored_services": list(MONITORED_SERVICES),
        "mounts": _mounts(),
        "tools": {
            "docker": _command_version("docker"),
            "git": _command_version("git"),
            "python": _command_version("python3", ["--version"]) if os.name != "nt" else _command_version("python", ["--version"]),
            "systemctl": _command_version("systemctl", ["--version"]),
        },
    }
