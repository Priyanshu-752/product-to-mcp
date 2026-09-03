# Deployment Readiness Checklist

This document separates **deployment-ready prototype** from **full SaaS
production readiness**.

## Current target

For the next deployment, the goal is:

- deploy the backend behind public HTTPS;
- deploy the frontend;
- connect frontend to backend;
- generate an MCP from OpenAPI;
- test generated tools;
- publish the public MCP URL to Smithery.

This is enough for a controlled demo or internal validation. It is not yet a
fully secure multi-tenant SaaS.

## Backend deployment requirements

Set these environment variables in the backend hosting platform:

```text
PRODUCT_TO_MCP_ENV=production
PRODUCT_TO_MCP_DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE
PRODUCT_TO_MCP_PUBLIC_BASE_URL=https://api.your-domain.com
PRODUCT_TO_MCP_CORS_ORIGINS=https://app.your-domain.com
PRODUCT_TO_MCP_ALLOWED_HOSTS=api.your-domain.com
PRODUCT_TO_MCP_SMITHERY_API_URL=https://api.smithery.ai
PRODUCT_TO_MCP_MAX_OPENAPI_BYTES=20971520
PRODUCT_TO_MCP_MCP_BEARER_TOKEN=replace-with-long-random-token
PRODUCT_TO_MCP_SECRET_ENCRYPTION_KEY=replace-with-long-random-secret
```

Important:

- `PRODUCT_TO_MCP_PUBLIC_BASE_URL` must point to the backend, not the frontend.
- Smithery needs a public `https://` MCP URL.
- Render-hosted backend services should use the Render Postgres internal URL
  when available. External Render Postgres URLs also work, and the backend
  enforces `sslmode=require` for external Render hosts when it is omitted.
- The bearer token is only a temporary deployment safety layer.
- Keep `PRODUCT_TO_MCP_SECRET_ENCRYPTION_KEY` stable. Changing it makes
  already-stored upstream API credentials unreadable.
- For the first Smithery URL-publish validation, leave
  `PRODUCT_TO_MCP_MCP_BEARER_TOKEN` blank unless the Smithery publisher is
  extended to send compatible auth config.
- Production should use proper MCP OAuth/access control.

## Frontend deployment requirements

Set this when frontend and backend are deployed separately:

```text
VITE_PRODUCT_TO_MCP_API_BASE_URL=https://api.your-domain.com
```

If the frontend and backend are served from the same domain/reverse proxy, this
can be left empty and the frontend will use same-origin API calls.

## Smoke test after deployment

Backend:

```bash
curl https://api.your-domain.com/healthz
curl https://api.your-domain.com/readyz
```

Or from PowerShell:

```powershell
.\scripts\check-deployment.ps1 -BackendUrl https://api.your-domain.com
```

Expected:

- `/healthz` returns `status: ok`;
- `/readyz` returns `database: ok`;
- `/readyz` shows `public_base_url_https: true`.

Frontend:

1. Open the deployed frontend.
2. Create a project.
3. Upload `examples/demo-openapi.yaml`.
4. Select generated tools.
5. Generate release.
6. Confirm Step 4 shows a public HTTPS MCP URL.
7. Test at least one generated tool.
8. Enter Smithery namespace, server name, and Smithery API key.
9. Publish to Smithery.
10. Verify Smithery returns status and MCP URL.

## What has been made deployment-safe now

- Configurable public backend URL.
- Configurable frontend CORS origins.
- Configurable allowed backend hosts.
- Health and readiness endpoints.
- Readiness checks storage access and reports the configured backend type.
- Dockerfile production command and healthcheck.
- PostgreSQL-backed project, source, release, and encrypted upstream secret
  storage.
- Frontend can call a separate deployed backend.
- Release responses include the public MCP URL used for Smithery.
- Optional MCP bearer token protection.
- Smithery publish section in Step 4.

## Still required for full production

These are not optional for a real customer-facing SaaS:

1. User accounts, login, organizations, and project ownership.
2. Control-plane API authorization for all `/v1/*` routes.
3. Formal migration tooling for schema evolution.
4. Managed KMS/Vault-backed secrets.
5. Proper MCP caller OAuth/access-control flow.
6. Smithery deployment records and status polling.
7. Rate limiting and abuse protection.
8. Audit logs for credential changes, release creation, and publishing.
9. Background jobs for validation, publishing, retries, and rollbacks.
10. Per-tenant isolation and permission model.
11. Observability: structured logs, metrics, tracing, alerts.
12. Backup/restore process for storage.

## Deployment decision

Use the current code for:

- internal demo;
- investor/team prototype;
- controlled customer discovery;
- Smithery URL-publish validation.

Do not use it yet for:

- public self-serve signups;
- multiple real customer tenants;
- long-lived customer credentials;
- sensitive production data access.
