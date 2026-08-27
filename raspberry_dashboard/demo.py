from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def demo_status() -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "online": True,
        "timestamp": timestamp,
        "hostname": "imagine3d-pi",
        "platform": "Linux-raspberrypi-aarch64-with-glibc",
        "python": "3.12.6",
        "machine": "aarch64",
        "processor": "Cortex-A76",
        "cpu_count": 4,
        "uptime": {"seconds": 496920, "human": "5d 18h 2m"},
        "load_average": [0.18, 0.11, 0.08],
        "memory": {"total_mb": 8062, "available_mb": 7318, "used_percent": 9.2},
        "disk": {"total_gb": 234.4, "free_gb": 214.2, "used_percent": 4.6},
        "temperature_c": 53.5,
        "monitor": {"started_at": "2026-08-27T12:00:00Z"},
        "instagram": {
            "running": True,
            "health_url": "http://127.0.0.1:8000/health",
            "health": {
                "ok": True,
                "status_code": 200,
                "latency_ms": 42,
                "payload": {
                    "messages_sent": 17,
                    "comments_seen": 84,
                    "delivery_failures": 0,
                },
            },
        },
        "tunnel": {
            "url": "https://demo.trycloudflare.com",
            "webhook_url": "https://demo.trycloudflare.com/webhook",
        },
        "services": [
            {
                "name": "instagram-stl-auto-dm",
                "active": True,
                "active_state": "active",
                "enabled_state": "enabled",
                "sub_state": "running",
                "main_pid": "1242",
                "started_at": "Thu 2026-08-27 09:12:44 -03",
                "restarts": "0",
                "restart_allowed": True,
            },
            {
                "name": "instagram-stl-auto-dm-tunnel",
                "active": True,
                "active_state": "active",
                "enabled_state": "enabled",
                "sub_state": "running",
                "main_pid": "1307",
                "started_at": "Thu 2026-08-27 09:12:48 -03",
                "restarts": "1",
                "restart_allowed": True,
            },
        ],
        "deploys": demo_deploys(),
        "notifications": demo_notifications(),
    }


def demo_logs(service_name: str) -> dict[str, Any]:
    return {
        "service": service_name,
        "ok": True,
        "return_code": 0,
        "lines": [
            "2026-08-27T15:12:01-03:00 imagine3d-pi service[1242]: health check ok latency=42ms",
            "2026-08-27T15:12:08-03:00 imagine3d-pi service[1242]: comment keyword matched post=demo-reel user=demo-user",
            "2026-08-27T15:12:09-03:00 imagine3d-pi service[1242]: direct message queued template=stl-link",
            "2026-08-27T15:12:10-03:00 imagine3d-pi service[1242]: delivery ok messages_sent=17 failures=0",
        ],
    }


def demo_deploys() -> list[dict[str, Any]]:
    return [
        {
            "name": "instagram-auto-dm",
            "path": "/opt/instagram-stl-auto-dm",
            "service": "instagram-stl-auto-dm",
            "branch": "main",
            "command": "git pull --ff-only",
            "actions_enabled": False,
        },
        {
            "name": "dashboard",
            "path": "/opt/raspberry-service-dashboard",
            "service": "raspberry-service-dashboard",
            "branch": "main",
            "command": "git pull --ff-only",
            "actions_enabled": False,
        },
    ]


def demo_notifications() -> dict[str, Any]:
    return {
        "enabled": True,
        "test_enabled": False,
        "channel": "webhook",
        "redaction": "enabled",
    }


def demo_inventory() -> dict[str, Any]:
    return {
        "label": "portfolio-demo",
        "model": "Raspberry Pi 5 Model B Rev 1.0",
        "ip_addresses": ["192.0.2.105"],
        "monitored_services": ["instagram-stl-auto-dm", "instagram-stl-auto-dm-tunnel"],
        "mounts": [
            {"mount": "/", "total_gb": 234.4, "free_gb": 214.2, "used_percent": 4.6},
            {"mount": "/boot/firmware", "total_gb": 0.5, "free_gb": 0.4, "used_percent": 19.8},
        ],
        "tools": {
            "docker": {"installed": True, "path": "/usr/bin/docker", "version": "Docker version 27.5.1"},
            "git": {"installed": True, "path": "/usr/bin/git", "version": "git version 2.43.0"},
            "python": {"installed": True, "path": "/usr/bin/python3", "version": "Python 3.12.6"},
            "systemctl": {"installed": True, "path": "/usr/bin/systemctl", "version": "systemd 255"},
        },
    }
