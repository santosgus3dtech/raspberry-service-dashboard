# Public and Private Strategy

The project should stay split into two layers:

## Public Portfolio Repo

Repository: `raspberry-service-dashboard`

Purpose:

- Show the reusable dashboard product.
- Keep clean code, tests, examples, and docs.
- Demonstrate the architecture and security model.
- Provide fake/example configuration only.

Safe to publish:

- Source code.
- `.env.example`.
- Example deploy target names.
- Redacted screenshots.
- Docs and diagrams.
- Tests.

Do not publish:

- Real `.env`.
- Personal domains and IPs.
- SSH usernames or hosts.
- Real service names that reveal private infrastructure.
- Webhook URLs.
- API tokens.
- Raw production logs.

## Private Overlay Repo

Recommended name: `gustavo-raspberry-private`

Purpose:

- Hold personal deployment settings.
- Track private operational scripts.
- Keep local service names, domains, and paths.
- Store private docs for your own Raspberry setup.

Suggested structure:

```text
gustavo-raspberry-private/
  README.md
  .gitignore
  env/
    dashboard.env.example
    dashboard.env
  deploy/
    install-dashboard.ps1
    sync-to-raspberry.ps1
  docs/
    operations.md
    services.md
```

The private repo can reference the public repo as the app source. That keeps portfolio work clean while still letting the real Raspberry evolve quickly.

## Workflow

1. Build features in the public repo using fake/sample config.
2. Keep all sensitive values in the private overlay.
3. Deploy the public app code to the Raspberry.
4. Copy only the private environment file to `/etc/raspberry-service-dashboard/dashboard.env`.
5. Use screenshots with redacted values for the public README.

This makes the GitHub profile easier to understand: public repos are polished products or case studies, private repos are personal operations overlays.
