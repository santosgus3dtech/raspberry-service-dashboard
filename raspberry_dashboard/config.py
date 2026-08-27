from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


DEFAULT_SERVICES = "instagram-stl-auto-dm,instagram-stl-auto-dm-tunnel"
DEFAULT_INSTAGRAM_HEALTH_URL = "http://127.0.0.1:8000/health"


def split_env(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "enabled"}


MONITORED_SERVICES = split_env("MONITORED_SERVICES", DEFAULT_SERVICES)
RESTARTABLE_SERVICES = set(split_env("RESTARTABLE_SERVICES", DEFAULT_SERVICES))
DEPLOY_ACTIONS_ENABLED = env_flag("DEPLOY_ACTIONS_ENABLED")
NOTIFICATION_TEST_ENABLED = env_flag("NOTIFICATION_TEST_ENABLED")
INSTAGRAM_HEALTH_URL = os.getenv("INSTAGRAM_HEALTH_URL", DEFAULT_INSTAGRAM_HEALTH_URL)
INVENTORY_EXTRA_LABEL = os.getenv("INVENTORY_EXTRA_LABEL", "portfolio-safe")
HOST_PROC = os.getenv("HOST_PROC", "/proc")
HOST_SYS = os.getenv("HOST_SYS", "/sys")
HOST_ROOT = os.getenv("HOST_ROOT", "/")
DEMO_MODE = env_flag("DEMO_MODE")


@dataclass(frozen=True)
class DeployTarget:
    name: str
    path: str
    service: str | None = None
    branch: str | None = None
    command: list[str] | None = None

    @property
    def command_display(self) -> str:
        if not self.command:
            return "git pull --ff-only && systemctl restart <service>"
        return " ".join(self.command)


def _target_from_mapping(item: dict[str, Any]) -> DeployTarget:
    name = str(item.get("name", "")).strip()
    path = str(item.get("path", "")).strip()
    service = str(item.get("service", "")).strip() or None
    branch = str(item.get("branch", "")).strip() or None
    raw_command = item.get("command")
    command = raw_command if isinstance(raw_command, list) else None

    if not name or not path:
        raise ValueError("Deploy target requires name and path.")

    return DeployTarget(
        name=name,
        path=path,
        service=service,
        branch=branch,
        command=[str(part) for part in command] if command else None,
    )


def deploy_targets() -> list[DeployTarget]:
    raw = os.getenv("DEPLOY_TARGETS_JSON", "").strip()
    if raw:
        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise ValueError("DEPLOY_TARGETS_JSON must be a list.")
        return [_target_from_mapping(item) for item in payload if isinstance(item, dict)]

    legacy_path = os.getenv("DEPLOY_PROJECT_PATH", "").strip()
    legacy_service = os.getenv("DEPLOY_SERVICE", "").strip()
    if legacy_path and legacy_service:
        return [
            DeployTarget(
                name=legacy_service,
                path=legacy_path,
                service=legacy_service,
                branch=os.getenv("DEPLOY_BRANCH", "").strip() or None,
            )
        ]

    return []
