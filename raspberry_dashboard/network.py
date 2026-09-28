from __future__ import annotations

import http.client
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


PISENTINEL_URL = os.getenv("PISENTINEL_URL", "http://127.0.0.1:8090/api/summary")
MAX_SUMMARY_BYTES = 128 * 1024


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def network_summary() -> dict[str, Any]:
    """Read the configured PiSentinel only; callers cannot supply a target URL."""
    unavailable = {
        "available": False,
        "status": "unavailable",
        "detail": "PiSentinel indisponível. Não foi possível consultar o resumo da rede.",
    }
    try:
        target = urllib.parse.urlsplit(PISENTINEL_URL)
        if target.scheme not in {"http", "https"} or not target.hostname:
            return unavailable
        # Avoid environment proxy settings and redirects changing the configured
        # destination. The fixed backend is never derived from request input.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirects())
        request = urllib.request.Request(PISENTINEL_URL, headers={"Accept": "application/json"})
        with opener.open(request, timeout=2) as response:
            if not 200 <= response.status < 300:
                return unavailable
            body = response.read(MAX_SUMMARY_BYTES + 1)
        if len(body) > MAX_SUMMARY_BYTES:
            return unavailable
        payload = json.loads(body)
        if not isinstance(payload, dict):
            return unavailable
        if not all(isinstance(payload.get(key), dict) for key in ("network", "collector", "counts")):
            return unavailable
        if not isinstance(payload["collector"].get("stale"), bool):
            return unavailable
        if not all(
            type(payload["counts"].get(key)) is int and payload["counts"][key] >= 0
            for key in ("devices", "online", "offline", "unknown", "open_incidents")
        ):
            return unavailable
        return {"available": True, "status": "available", "summary": payload}
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError, UnicodeError):
        return unavailable
