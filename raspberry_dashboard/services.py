from __future__ import annotations

import time
from typing import Any

from fastapi import HTTPException

from .command import run
from .config import MONITORED_SERVICES, RESTARTABLE_SERVICES


def monitored_service_names() -> list[str]:
    return list(MONITORED_SERVICES)


def known_services() -> set[str]:
    return set(MONITORED_SERVICES) | RESTARTABLE_SERVICES


def assert_known_service(name: str) -> None:
    if name not in known_services():
        raise HTTPException(status_code=404, detail="Unknown service.")


def assert_actionable_service(name: str) -> None:
    if name not in RESTARTABLE_SERVICES:
        raise HTTPException(status_code=403, detail="Restart is not allowed for this service.")


def parse_key_values(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def service_status(name: str) -> dict[str, Any]:
    active = run(["systemctl", "is-active", name])
    enabled = run(["systemctl", "is-enabled", name])
    show = run(
        [
            "systemctl",
            "show",
            name,
            "--property=LoadState,ActiveState,SubState,UnitFileState,MainPID,ActiveEnterTimestamp,NRestarts",
        ],
    )
    props = parse_key_values(show.stdout)

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
        "restart_allowed": name in RESTARTABLE_SERVICES,
    }


def restart_service(name: str) -> dict[str, Any]:
    assert_known_service(name)
    assert_actionable_service(name)

    result = run(["sudo", "-n", "systemctl", "restart", name], timeout=20)
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=(result.stderr or result.stdout or "Failed to restart service.").strip(),
        )

    time.sleep(1)
    return {
        "service": name,
        "ok": True,
        "status": service_status(name),
    }
