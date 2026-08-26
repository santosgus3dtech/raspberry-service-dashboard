# Raspberry Service Dashboard

FastAPI dashboard for monitoring services on a Raspberry Pi. It shows uptime, memory, disk, temperature, service states, health check latency, tunnel URL, logs, and controlled restart actions.

This repo was extracted from a real Raspberry deployment used to keep a production automation visible and recoverable from a small web UI.

## Features

- `/api/status` JSON endpoint for system and service health.
- `/api/logs/{service}` with token redaction before logs reach the browser.
- Optional `/api/services/{service}/restart` for allowlisted services.
- Responsive single-file dashboard UI served by FastAPI.
- systemd unit example for deployment on a Raspberry Pi.
- Tests for service allowlisting and log redaction.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn raspberry_dashboard.app:app --reload
```

Open `http://127.0.0.1:8000`.

## Configuration

```bash
MONITORED_SERVICES=instagram-stl-auto-dm,instagram-stl-auto-dm-tunnel
RESTARTABLE_SERVICES=instagram-stl-auto-dm,instagram-stl-auto-dm-tunnel
INSTAGRAM_HEALTH_URL=http://127.0.0.1:8000/health
```

Only services listed in `RESTARTABLE_SERVICES` can be restarted from the UI. Unknown services return `404`, and non-allowlisted services return `403`.

## Deploy on Raspberry Pi

Copy the project to `/opt/raspberry-service-dashboard`, create a virtual environment, install requirements, and adapt:

```text
deploy/raspberry-service-dashboard.service
```

Then install with systemd:

```bash
sudo cp deploy/raspberry-service-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now raspberry-service-dashboard
```

## Portfolio

This is a useful standalone project because it shows operational tooling: Linux/systemd integration, safe service actions, log redaction, health checks, and a web interface for a headless device.
