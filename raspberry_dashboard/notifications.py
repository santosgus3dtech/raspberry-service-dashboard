from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from fastapi import HTTPException

from .config import NOTIFICATION_TEST_ENABLED
from .redaction import redact


def notification_config() -> dict[str, Any]:
    return {
        "enabled": bool(os.getenv("NOTIFICATION_WEBHOOK_URL")),
        "test_enabled": NOTIFICATION_TEST_ENABLED,
        "channel": os.getenv("NOTIFICATION_CHANNEL", "webhook"),
        "redaction": "enabled",
    }


def send_notification(title: str, message: str, severity: str = "info") -> dict[str, Any]:
    webhook_url = os.getenv("NOTIFICATION_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return {"ok": False, "skipped": True, "reason": "Notification webhook is not configured."}

    payload = {
        "title": redact(title),
        "message": redact(message),
        "severity": severity,
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return {"ok": 200 <= response.status < 300, "status_code": response.status}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": str(exc)}


def send_test_notification() -> dict[str, Any]:
    if not NOTIFICATION_TEST_ENABLED:
        raise HTTPException(status_code=403, detail="Notification test is disabled.")
    return send_notification(
        "Raspberry dashboard test",
        "The notification channel is reachable from the dashboard.",
        "info",
    )
