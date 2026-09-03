# Product-to-MCP Prototype and Implementation Plan

## Objective

First build a working browser-based prototype where a user provides an API,
reviews generated tools, creates a real MCP endpoint, tests it, and publishes
it to Smithery. Once that complete path works, extend the same contracts to
PostgreSQL and Supabase and then harden the system for production.

The first milestone must produce visible working software, not only backend
architecture modules.

## Decisions

- OpenAPI is the prototype source type.
- PostgreSQL and Supabase are the next source types after the API prototype.
- GET/HEAD operations were supported first.
- CRUD API operations are now supported in the prototype for GET, HEAD, POST, PUT, PATCH, and DELETE.
- Write operations must still be treated as higher-risk and need explicit user selection, credentials, validation, and audit controls before production.
- The customer’s upstream API connection is owner-shared.
- The runtime uses immutable manifests, not generated customer code.
- The prototype uses one FastAPI deployment for control APIs and MCP endpoints.
- The production target remains a managed multi-tenant MCP gateway.
- Smithery publishing uses the customer’s namespace and API key. The prototype
  publish form must not persist the Smithery API key.
- MCP tools come first; resources, prompts, writes, and triggers come later.

## Prototype user journey

```text
Open frontend
  -> create project
  -> enter API base URL
  -> upload/paste OpenAPI JSON or YAML
  -> backend discovers supported operations
  -> user selects generated CRUD tools
  -> optionally enter upstream API key
  -> generate immutable MCP release
  -> test tools in frontend/MCP Inspector
  -> deploy MCP endpoint to public HTTPS
  -> enter Smithery namespace/name/key
  -> publish to Smithery
  -> call the published MCP
```

## Prototype technology stack

- React, TypeScript, and Vite frontend.
- Python 3.11 and FastAPI backend.
- Minimal MCP-compatible Streamable HTTP handler for the prototype, followed by
  official SDK compatibility validation before production.
- SQLite for prototype projects, source revisions, tools, releases, and audit
  records.
- HTTPX for upstream API execution and Smithery API calls.
- Pydantic and JSON Schema for validation.
- Docker Compose for one-command local startup.
- Pytest, Vitest, and one browser end-to-end test.

The backend modules remain separated by responsibility so they can later move
into independent control-plane, worker, and gateway processes.

## Phase 0 — Create the runnable project structure

Create the real `backend`, `frontend`, `examples`, and test folders defined in
`docs/03-product-architecture-and-flows.md`.

Deliver:

- backend and frontend dependency manifests;
- FastAPI app with `/healthz` and `/readyz`;
- Vite application shell;
- SQLite database initialization;
- `.env.example` containing names/defaults but no secrets;
- Docker Compose local startup;
- one local demo API and `examples/demo-openapi.yaml`;
- backend and frontend smoke tests;
- a README run command and expected URLs.

Acceptance: one command starts the frontend, backend, and demo API. The browser
shows backend health and an empty project list.

## Phase 1 — Working OpenAPI import flow

Build the first visible product workflow:

- create and view a project;
- enter an API base URL;
- upload or paste OpenAPI 3.0/3.1 JSON/YAML;
- optionally enter an upstream API key through a secret field;
- parse and validate the document;
- resolve supported local references;
- discover GET/HEAD/POST/PUT/PATCH/DELETE operations;
- generate stable tool names and input schemas;
- show method, path, description, parameters, and support status;
- let the user enable or disable each supported operation;
- persist the exact source revision and selected policy.

Unsupported references, authentication modes, schemas, and HTTP methods must be
shown clearly as unsupported instead of guessed.

Acceptance: importing the demo OpenAPI file shows its CRUD operations in the
browser with selectable generated tool definitions.

## Phase 2 — Generate and run the MCP

Implement:

- deterministic compilation from selected operations to an immutable manifest;
- source and manifest SHA-256 hashes;
- one release and deployment slug per generated MCP;
- `POST` and `GET /mcp/{deployment_slug}/mcp`;
- MCP initialization and capability negotiation;
- `tools/list` and `tools/call`;
- JSON Schema argument validation;
- safe mapping from tool arguments to the approved HTTP request;
- safe JSON request-body forwarding for approved CRUD operations;
- server-side API-key injection where configured;
- exactly one upstream request per accepted tool call;
- response-size and timeout limits;
- structured MCP results and safe error results;
- redacted call records;
- a frontend test panel for listing and calling generated tools.

The MCP runtime must not let a caller choose an arbitrary URL, HTTP method,
header, credential, operation, or release.

Acceptance: a user imports `examples/demo-openapi.yaml`, creates an MCP, sees
its tools in the frontend and MCP Inspector, and successfully calls the demo
API.

## Phase 2.5 - CRUD and credential-aware prototype path

Implemented after the initial read-only prototype:

- discover GET, HEAD, POST, PUT, PATCH, and DELETE from OpenAPI;
- map JSON request bodies into MCP tool arguments under `body`;
- execute approved CRUD tools against the configured API base URL;
- keep bearer/API-key credential injection server-side;
- expose JSON argument textareas in the frontend test panel;
- extend the demo API and dummy OpenAPI file with create, replace, update, and
  delete product operations;
- keep OPTIONS unsupported.

Acceptance: the local demo project can generate MCP tools for list, get,
create, replace, update, and delete operations and test them from the frontend.

Next phase: deploy the backend behind public HTTPS, verify the MCP endpoint
with an external MCP client/Smithery flow, and publish the generated MCP into a
Smithery namespace. After that is proven, PostgreSQL and Supabase adapters can
start as the next source types.

## Phase 3 — Deploy publicly and publish to Smithery

Implement:

- production container builds for the prototype;
- deployment of the backend to a public HTTPS host;
- a publish-readiness check using MCP initialization and `tools/list`;
- frontend fields for Smithery namespace, server name, and API key;
- a backend Smithery adapter that submits the public MCP URL through the
  Smithery release API;
- deployment status, MCP URL, warnings, and retryable failure display;
- immediate disposal of the submitted Smithery API key after the request;
- verification that the server exists in the customer’s Smithery namespace.

Local development can generate and test the MCP, but Smithery publishing only
becomes available when the endpoint is reachable through public HTTPS.

Acceptance: a fresh API project is imported, released, deployed, published,
found in the customer’s Smithery namespace, and callable through Smithery.

## Phase 4 — Stabilize the prototype

- add friendly validation, empty, progress, and recovery states;
- protect stored upstream API credentials;
- enforce explicit approval policy for write/API mutation operations;
- add basic caller access tokens for generated MCPs;
- add per-release request limits;
- prove SQLite/release persistence across restart;
- add an end-to-end browser test for the complete workflow;
- document local development and hosted deployment;
- produce a short recorded demo and known-limitations list.

This phase marks the prototype complete. It does not make the service
production-ready.

## Phase 5 — PostgreSQL and Supabase sources

These adapters reuse the source inventory, capability policy, manifest,
release, gateway, and audit contracts proven by the OpenAPI prototype.

### PostgreSQL

- connect using TLS and a dedicated read-only role;
- verify read-only behavior;
- introspect selected schemas, tables, columns, and relationships;
- let the user select tables, fields, filters, sorting, and limits;
- generate parameterized list/get/search tools;
- prohibit unrestricted SQL, writes, DDL, and arbitrary stored procedures.

### Supabase

- validate the project URL and supported key configuration;
- use PostgREST/REST first so Row Level Security remains in the request path;
- discover configured tables, views, and approved RPCs;
- let the user select fields, filters, and limits;
- generate curated read-only tools;
- prohibit browser exposure of service credentials;
- document and test expected RLS behavior.

## Phase 6 — Production control plane and tenancy

Replace prototype-only infrastructure with:

- workspace/project ownership and tenant-scoped authorization;
- PostgreSQL control-plane persistence and migrations;
- object storage for immutable source artifacts;
- durable source-processing jobs and workers;
- external secret manager and credential rotation;
- immutable release records and atomic deployment pointers;
- customer and MCP-caller authentication;
- searchable redacted audit events.

Every source revision and release must be immutable, hash-addressed, and
independently retrievable after service restart.

## Phase 7 — Separate production MCP gateway

Move the gateway into a stateless independently scalable process with:

- OAuth protected-resource metadata;
- caller token audience and scope validation;
- deployment/release resolution;
- immutable manifest loading and bounded caching;
- API/PostgreSQL/Supabase adapter dispatch;
- outbound HTTP and database safety limits;
- per-tenant quotas and rate limits;
- structured redacted audit events;
- health, readiness, and observability endpoints.

The gateway must not execute customer code and must not let a caller choose an
arbitrary URL, SQL statement, table, credential, or release.

## Phase 8 — Production hardening

Complete before describing the service as production-ready:

- tenant-isolation and authorization review;
- SSRF, DNS rebinding, redirect, and outbound-network controls;
- rate limits, quotas, billing measurements, and abuse handling;
- structured logs, traces, metrics, and alerts;
- backup and restore testing;
- release rollback and disaster recovery;
- secret rotation and revocation;
- security review and penetration test;
- privacy, retention, deletion, and incident-response policies;
- concurrent MCP client and upstream load testing;
- Smithery scanner compatibility and publishing recovery tests.

## Prototype API surface

```text
GET    /healthz
GET    /readyz
POST   /v1/projects
GET    /v1/projects
GET    /v1/projects/{project_id}
POST   /v1/projects/{project_id}/openapi
GET    /v1/projects/{project_id}/operations
PUT    /v1/projects/{project_id}/operations
POST   /v1/projects/{project_id}/releases
GET    /v1/releases/{release_id}
POST   /v1/releases/{release_id}/test
POST   /v1/releases/{release_id}/smithery/publish
GET    /v1/releases/{release_id}/smithery/status
POST   /mcp/{deployment_slug}/mcp
GET    /mcp/{deployment_slug}/mcp
```

## Required prototype tests

- valid and invalid OpenAPI JSON/YAML;
- operation-name collisions;
- supported query/path/header parameters;
- disabled and write-operation rejection;
- tool argument validation;
- API-key injection without secret exposure;
- upstream timeout, 4xx, 5xx, malformed, and oversized responses;
- source and manifest immutability;
- restart persistence;
- MCP initialization, `tools/list`, and `tools/call`;
- exactly one upstream request for one accepted call;
- Smithery publish success, warning, invalid-key, and retryable failure paths;
- full browser journey from project creation through MCP test.

## Prototype acceptance criteria

The prototype is complete when a user can:

1. open the frontend;
2. create a project;
3. upload or paste an OpenAPI definition and base URL;
4. review and select generated CRUD operations;
5. generate an immutable MCP release;
6. list and call its tools through the frontend and MCP Inspector;
7. deploy the endpoint to public HTTPS;
8. publish it to their Smithery namespace from the product;
9. call the published MCP through Smithery.

## Full initial product acceptance

The broader initial product is complete when a customer can:

1. import an API or configure PostgreSQL/Supabase;
2. see the discovered inventory;
3. select read-only capabilities and fields;
4. configure a server-side credential;
5. pass a connection test;
6. create and deploy an immutable MCP release;
7. connect an MCP client and call approved tools;
8. observe redacted audit records;
9. publish the endpoint in their Smithery namespace;
10. update a source and receive a new release without mutating the old one.

## Relationship to `saastoagent`

The existing `saastoagent` work provides reusable patterns for source
revisions, OpenAPI ingestion, ToolRouter discovery, durable jobs, credential
references, safe API execution, redacted evidence, and immutable deployment
lineage. It should be used as implementation evidence and as a source of
adapters where contracts match.

The prototype should not import Corpus RouteDeck UI state or the full agent
runtime. It needs a small direct path from OpenAPI to manifest to MCP tool
execution. Production can then adopt the proven persistence, worker, secret,
and isolation patterns behind explicit Product-to-MCP interfaces.

## Definition of production-ready

Production-ready means more than “the MCP Inspector can call a tool.” It means
the platform can prove, under failure and adversarial input, that every call is
authorized, scoped to one immutable release, limited to an approved operation,
safe for the configured source, observable without leaking secrets, and
recoverable without losing tenant or release truth.
