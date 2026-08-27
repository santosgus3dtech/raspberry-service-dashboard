# Security Model

This dashboard is meant to be useful without becoming an unrestricted remote shell.

## Read Paths

The dashboard reads:

- `/proc` and `/sys` for system metrics.
- `systemctl` for service state.
- `journalctl` for allowlisted service logs.
- Optional local HTTP health endpoints.
- Optional host inventory metadata.

## Write or Action Paths

Actions are narrow and disabled unless explicitly configured:

- Restart requires the service to be in `RESTARTABLE_SERVICES`.
- Deploy requires the target to be in `DEPLOY_TARGETS_JSON`.
- Deploy execution also requires `DEPLOY_ACTIONS_ENABLED=true`.
- Notification tests require `NOTIFICATION_TEST_ENABLED=true`.

## Log Redaction

Logs pass through redaction before the browser sees them. Current redaction covers:

- `access_token=` query values.
- `hub.verify_token=` values.
- `VERIFY_TOKEN=`, `META_APP_SECRET=`, and `IG_ACCESS_TOKEN=`.
- `Authorization: Bearer ...`.
- Long Instagram tokens starting with `IGAA`.
- Generic `password=`, `secret=`, `token=`, and `api_key=` style values.

## Recommended Deployment

- Run behind a trusted reverse proxy.
- Put private config in `/etc/raspberry-service-dashboard/dashboard.env`.
- Use least-privilege sudo rules for specific `systemctl restart <service>` actions.
- Do not expose this dashboard publicly without authentication.
- Do not mount `/var/run/docker.sock` into this app.
- Do not add a browser terminal unless it is heavily scoped and authenticated.
