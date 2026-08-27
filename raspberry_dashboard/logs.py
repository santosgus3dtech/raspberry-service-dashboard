from __future__ import annotations

from typing import Any

from .command import run
from .redaction import redact
from .services import assert_known_service


def service_logs(name: str, limit: int = 120) -> dict[str, Any]:
    assert_known_service(name)
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
    result = run(command, timeout=5)
    if result.returncode != 0:
        result = run(["sudo", "-n", *command], timeout=5)

    output = (result.stdout or result.stderr or "").strip()
    raw_lines = output.splitlines()[-safe_limit:] if output else []
    lines = [redact(line) for line in raw_lines]
    return {
        "service": name,
        "ok": result.returncode == 0,
        "return_code": result.returncode,
        "lines": lines,
    }
