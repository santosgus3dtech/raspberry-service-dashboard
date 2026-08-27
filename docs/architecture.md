# Architecture

Raspberry Service Dashboard is a small FastAPI app designed for headless Raspberry Pi operations. The public repository keeps the reusable app code and documentation; private deployment values are injected by environment variables.

## Runtime Flow

```mermaid
flowchart LR
  Browser[Browser UI] --> API[FastAPI app]
  API --> Metrics[metrics.py]
  API --> Services[services.py]
  API --> Logs[logs.py]
  API --> Deploys[deploys.py]
  API --> Notifications[notifications.py]
  API --> Inventory[inventory.py]
  API --> Health[health.py]

  Metrics --> Proc[/proc and /sys]
  Services --> Systemd[systemctl]
  Logs --> Journal[journalctl]
  Deploys --> Git[git pull]
  Deploys --> Restart[systemctl restart]
  Notifications --> Webhook[optional webhook]
  Inventory --> Host[host tools and mounts]
  Health --> LocalApp[local health endpoint]
```

## Public Modules

- `app.py`: API route registration and status composition.
- `metrics.py`: uptime, memory, disk, temperature, load average, Python and platform metadata.
- `services.py`: systemd status and allowlisted restart behavior.
- `logs.py`: journalctl reader with redaction.
- `redaction.py`: shared secret/token redaction patterns.
- `deploys.py`: allowlisted deploy targets, disabled by default.
- `notifications.py`: notification channel visibility and optional test.
- `inventory.py`: public-safe device inventory.
- `health.py`: HTTP health checks and tunnel discovery.
- `config.py`: environment variables and deploy target parsing.
- `ui.py`: single-file browser dashboard.

## Data Boundaries

The UI only reads from the API. The API only exposes values that are either system metrics, allowlisted service names, or sanitized outputs. Real deployment details are not committed to this repo.

Actions are intentionally narrow:

- Restart works only for services listed in `RESTARTABLE_SERVICES`.
- Deploy works only for targets listed in `DEPLOY_TARGETS_JSON`.
- Deploy execution is blocked unless `DEPLOY_ACTIONS_ENABLED=true`.
- Notification test is blocked unless `NOTIFICATION_TEST_ENABLED=true`.

## Portfolio Narrative

This architecture is intentionally simple: one process, no database, no agent with broad shell access, no direct terminal in the browser, and no raw Docker socket. It demonstrates practical operations tooling without making the dashboard an unrestricted remote control panel.
