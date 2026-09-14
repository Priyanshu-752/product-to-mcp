# Product-to-MCP

Product-to-MCP is a managed platform that helps a product owner expose a safe,
versioned MCP server for their product API.

The first release supports:

- OpenAPI-based HTTP APIs;
- agent actions built from API operations;
- automatically derived API toolsets that filter agent-visible tools, plus optional chained actions;
- validation and safer write-action policies;
- immutable releases served by a managed Streamable HTTP gateway;
- customer-owned Smithery publishing from the prototype UI.

## Prototype-first milestone

Before implementing the complete production architecture, we will build a
small working product that can be opened in the browser:

1. the user enters a project name, API base URL, and OpenAPI JSON/YAML;
2. the backend derives toolsets from OpenAPI tags or paths;
3. the user selects which API toolsets the agent receives and may create single-call actions or safe one-write chains;
4. approved actions can be added to a focused publishing profile;
5. the backend previews and compiles the selected API tools and actions into an immutable manifest;
6. the generated MCP exposes exactly those tools at a Streamable HTTP endpoint;
7. the frontend tests every generated tool before the URL is published to Smithery.

The prototype uses one repository, one frontend, one FastAPI backend, and
SQLite for local development. Hosted deployments can use PostgreSQL by setting
`PRODUCT_TO_MCP_DATABASE_URL` to a Postgres connection string. Multi-tenant
production storage, workers, and advanced authorization follow after this
end-to-end path is working.

This repository contains the working prototype, deterministic action layer,
product research, and implementation documentation. The documents are
separated so the protocol, architecture, operations, and release flow remain
easy to review.

## Documents

1. [MCP fundamentals](docs/01-mcp-fundamentals.md) — what MCP is and how a
   host, client, and server communicate.
2. [What an MCP builder needs](docs/02-what-is-needed-to-build-mcp.md) — the
   protocol, source adapters, security, runtime, and deployment requirements.
3. [Product architecture and flows](docs/03-product-architecture-and-flows.md)
   — the user journey, folder structure, backend flow, API shape, and Smithery
   publishing flow.
4. [Customer inputs and production readiness](docs/04-customer-inputs-and-production-readiness.md)
   — what customers provide, source-specific rules, risks, and readiness gates.
5. [Smithery deployment flow](docs/05-smithery-deployment-flow.md) — how the
   generated public MCP URL is published to Smithery.
6. [Deployment readiness checklist](docs/06-deployment-readiness-checklist.md)
   — env vars, smoke tests, and what still blocks full SaaS production.
7. [Implementation plan](plans/2026-08-26-product-to-mcp-plan.md) — phases,
   deliverables, testing, and acceptance criteria.

8. [Agent action system flow](docs/07-agent-action-system-flow.md)
   - the new API-only flow where customer APIs become grouped, chained,
     validated agent actions before MCP release generation.
9. [Deterministic MCP middle layer](docs/08-deterministic-mcp-middle-layer.md)
   - CTO-facing explanation of the current API-wrapper prototype, the new
     action-compilation layer, and the complete agent-action workflow.
10. [Action layer implementation reference](docs/09-action-layer-implementation-reference.md)
    - implemented models, validation rules, runtime outcomes, APIs, tests, and
      deployment compatibility notes.
11. [Agent-useful toolsets](plans/2026-09-14-agent-useful-toolsets.md)
    - OpenAPI-derived toolsets, release-time selection, compatibility, and tests.

## Local development

Use three PowerShell terminals from the repository root.

```powershell
# Terminal 1: customer demo API
python -m uvicorn main:app --app-dir examples/demo-api --host 127.0.0.1 --port 9000

# Terminal 2: Product-to-MCP backend
.\scripts\run-backend.ps1

# Terminal 3: Product-to-MCP frontend
.\scripts\run-frontend.ps1
```

Open `http://127.0.0.1:5173`, choose **No authentication**, and upload
`examples/demo-openapi.yaml`. Use `examples/large-openapi-50.yaml` to test the
large-catalog workflow.

Verification commands:

```powershell
cd backend
pytest -q

cd ..\frontend
npm.cmd test
npm.cmd run test:e2e
npm.cmd run build
npm.cmd audit --audit-level=low
```

## Core architectural decision

We will compile customer configuration into an immutable runtime manifest and
serve it from a hardened multi-tenant gateway. We will not execute customer
code or ask an LLM to generate executable server code in the production path.

The product owner supplies the upstream API connection. The generated MCP is
protected separately, and the upstream credential is kept server-side.
Therefore, owner-shared access must be clearly disclosed: authorized MCP users
operate against the data permissions of that owner API connection.
