from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .command import run
from .config import DEPLOY_ACTIONS_ENABLED, DeployTarget, deploy_targets
from .redaction import redact


def _target_map() -> dict[str, DeployTarget]:
    return {target.name: target for target in deploy_targets()}


def list_deploys() -> list[dict[str, Any]]:
    return [
        {
            "name": target.name,
            "path": target.path,
            "service": target.service,
            "branch": target.branch,
            "command": target.command_display,
            "actions_enabled": DEPLOY_ACTIONS_ENABLED,
        }
        for target in deploy_targets()
    ]


def run_deploy(name: str) -> dict[str, Any]:
    targets = _target_map()
    if name not in targets:
        raise HTTPException(status_code=404, detail="Unknown deploy target.")
    if not DEPLOY_ACTIONS_ENABLED:
        raise HTTPException(status_code=403, detail="Deploy actions are disabled.")

    target = targets[name]
    project_path = Path(target.path)
    if not project_path.exists():
        raise HTTPException(status_code=404, detail="Deploy path does not exist.")

    command = target.command or ["git", "pull", "--ff-only"]
    started = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        result = subprocess.CompletedProcess(command, 124, exc.stdout or "", exc.stderr or str(exc))

    restart_result = None
    if result.returncode == 0 and target.service:
        restart_result = run(["sudo", "-n", "systemctl", "restart", target.service], timeout=20)

    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return {
        "name": target.name,
        "ok": result.returncode == 0 and (restart_result is None or restart_result.returncode == 0),
        "elapsed_ms": elapsed_ms,
        "command": target.command_display,
        "return_code": result.returncode,
        "output": redact((result.stdout or result.stderr or "").strip())[-4000:],
        "restart": None
        if restart_result is None
        else {
            "service": target.service,
            "return_code": restart_result.returncode,
            "output": redact((restart_result.stdout or restart_result.stderr or "").strip())[-1000:],
        },
    }
