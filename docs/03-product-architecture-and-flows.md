# Product Architecture and Flows

## Product roles

### Platform operator

Operates Product-to-MCP, the control plane, the gateway, workers, storage,
monitoring, and security controls.

### Product owner/customer

Creates a project, supplies the API/database definition and connection,
selects exposed capabilities, reviews the release, and publishes the server in
their own Smithery namespace.

### MCP caller/end user

Connects an AI client to the published MCP and uses only the tools allowed by
the customer’s release and caller policy.

In the initial owner-shared mode, the caller uses the data access of the
owner’s upstream connection. This does not automatically create a separate
upstream identity for each caller.

## Prototype folder structure — build this first

The prototype must remain small enough that the full logic can be followed
from the browser form to the final API request. It uses one backend process for
the control API and generated MCP endpoints. The code is separated by
responsibility so those modules can later move into independent services.

```text
product-to-mcp/
├── README.md
├── docs/
├── plans/
├── .env.example
├── compose.yaml
├── backend/
│   ├── pyproject.toml
│   ├── src/product_to_mcp/
│   │   ├── main.py               # FastAPI application and lifespan
│   │   ├── config.py             # Environment settings
│   │   ├── api/
│   │   │   ├── projects.py       # Create/list prototype projects
│   │   │   ├── sources.py        # Upload and inspect OpenAPI
│   │   │   ├── releases.py       # Build/deploy MCP releases
│   │   │   └── smithery.py       # Publish/status endpoints
│   │   ├── domain/
│   │   │   ├── models.py         # Project, source, tool, release models
│   │   │   └── errors.py
│   │   ├── openapi/
│   │   │   ├── parser.py         # JSON/YAML parsing and validation
│   │   │   └── operations.py     # OpenAPI operation discovery
│   │   ├── compiler/
│   │   │   └── manifest.py       # Selected operations -> MCP manifest
│   │   ├── gateway/
│   │   │   ├── server.py         # MCP server creation
│   │   │   └── executor.py       # Manifest tool -> upstream HTTP call
│   │   ├── smithery/
│   │   │   └── publisher.py      # Smithery release API adapter
│   │   └── storage/
│   │       └── sqlite.py          # Prototype persistence
│   └── tests/
├── frontend/
│   ├── package.json
│   └── src/
│       ├── api.ts
│       ├── App.tsx
│       ├── pages/CreateProject.tsx
│       ├── pages/ReviewTools.tsx
│       ├── pages/Release.tsx
│       └── components/
└── examples/
    ├── demo-openapi.yaml
    └── demo-api/
```

## Production target folder structure

```text
product-to-mcp/
├── README.md
├── docs/
├── plans/
├── backend/
│   ├── pyproject.toml
│   ├── migrations/
│   ├── src/product_to_mcp/
│   │   ├── api/                  # Control-plane HTTP routes and DTOs
│   │   ├── auth/                 # Customer and MCP-caller auth
│   │   ├── projects/             # Tenant/project lifecycle
│   │   ├── sources/              # Source identity and immutable revisions
│   │   │   ├── api/              # OpenAPI source adapter
│   │   │   ├── postgres/         # PostgreSQL metadata and query adapter
│   │   │   └── supabase/         # Supabase PostgREST adapter
│   │   ├── compiler/              # Source -> validated MCP manifest
│   │   ├── manifests/             # Immutable release records and hashes
│   │   ├── secrets/               # Secret-manager port and adapters
│   │   ├── gateway/               # MCP protocol and tool execution
│   │   ├── smithery/              # Publish-readiness and API integration
│   │   ├── jobs/                  # Durable worker contracts
│   │   ├── audit/                 # Redacted audit and usage events
│   │   ├── storage/               # Database/object-storage ports
│   │   └── settings.py
│   └── tests/
├── frontend/
│   ├── src/features/projects/
│   ├── src/features/sources/
│   ├── src/features/releases/
│   └── src/features/smithery/
└── infra/
    ├── docker/
    ├── terraform/
    └── observability/
```

The prototype starts with one backend process. After the workflow is proven,
the API service, MCP gateway, and worker will share domain packages but run as
separate production processes. This keeps control-plane mutations away from
the low-latency data plane without slowing down the prototype.

## User interaction flow

1. Customer signs up and creates a workspace.
2. Customer creates a product project, such as `Acme Store`.
3. Customer selects a source type: OpenAPI, PostgreSQL, or Supabase.
4. Customer uploads an OpenAPI file or enters a database connection setup.
5. Product-to-MCP validates the source and creates an immutable source revision.
6. A worker discovers operations, schemas, tables, columns, and capabilities.
7. Customer reviews the discovered inventory.
8. Customer selects the exact tools/tables/fields to expose.
9. Customer configures the owner-side API or database credential.
10. Product-to-MCP performs a safe connection test.
11. The compiler creates an immutable MCP release manifest.
12. Customer reviews the generated tool names, descriptions, schemas, scopes,
    data policy, and read/write status.
13. Product-to-MCP deploys the release to the managed gateway.
14. The gateway is tested with the MCP SDK/Inspector contract.
15. Product-to-MCP shows the public endpoint and Smithery publish instructions.
16. Customer publishes the endpoint in their own Smithery namespace.
17. Customer verifies the Smithery scan and connects an MCP client.

## Control-plane backend flow

```text
HTTP API
  -> authenticate customer
  -> validate request and tenant ownership
  -> persist source/project state
  -> enqueue durable job

Worker
  -> load immutable source revision
  -> run source adapter
  -> normalize and validate source
  -> persist discovery artifacts
  -> expose reviewable inventory

Release request
  -> verify source readiness
  -> verify selected capabilities
  -> verify secret reference and policy
  -> compile deterministic manifest
  -> hash and persist manifest
  -> activate deployment pointer

MCP gateway
  -> authenticate MCP caller
  -> resolve deployment and release
  -> load manifest
  -> validate tools/call arguments
  -> execute approved source adapter
  -> redact result and emit audit event
  -> return MCP result
```

## Source-specific backend flow

### OpenAPI

```text
upload JSON/YAML
  -> parse and resolve references
  -> validate OpenAPI 3.0/3.1
  -> discover operations
  -> map supported security schemes
  -> owner selects operations
  -> compile API operation -> MCP tool
  -> execute safe HTTP request at runtime
```

### PostgreSQL

```text
connection setup
  -> TLS connection test
  -> read-only metadata discovery
  -> list schemas/tables/columns/relationships
  -> owner selects tables, fields, filters, and limits
  -> compile curated database tools
  -> execute parameterized read-only query
```

### Supabase

```text
project URL + approved key mode
  -> test PostgREST access
  -> inspect configured tables/views/RPCs
  -> verify expected Row Level Security behavior
  -> owner selects tables, fields, filters, and limits
  -> compile curated REST-backed tools
  -> execute through Supabase API with server-side credentials
```

## Public API shape

The control-plane API should use versioned JSON endpoints:

```text
POST   /v1/projects
GET    /v1/projects/{project_id}
POST   /v1/projects/{project_id}/source-revisions
POST   /v1/source-revisions/{revision_id}/validate
GET    /v1/source-revisions/{revision_id}/inventory
PATCH  /v1/projects/{project_id}/capability-policy
POST   /v1/projects/{project_id}/connections
POST   /v1/projects/{project_id}/connection-tests
POST   /v1/projects/{project_id}/releases
GET    /v1/releases/{release_id}
POST   /v1/releases/{release_id}/deploy
GET    /v1/deployments/{deployment_id}
GET    /v1/deployments/{deployment_id}/smithery-publish
```

The data-plane endpoint is separate:

```text
POST /mcp/{deployment_slug}/mcp
GET  /mcp/{deployment_slug}/mcp
```

## Important internal contracts

### Source revision

A source revision contains the original source hash, normalized source hash,
source type, discovery status, parser/compiler versions, and immutable artifact
references.

### Capability policy

A capability policy contains the explicit allowlist of API operations or
database capabilities, selected fields, safety class, caller scopes, rate
limits, and response limits.

### MCP release manifest

```text
release_id
project_id
source_revision_id
manifest_hash
server_name
server_version
tools[]
upstream_binding
caller_policy
redaction_policy
compiler_version
created_at
```

Each tool contains its MCP name, description, input/output schemas, source
mapping, safety class, timeout, and credential-reference ID. It never contains
the credential value.

## Smithery deployment flow

1. The customer approves a release.
2. Product-to-MCP deploys the immutable manifest to the managed gateway.
3. The gateway exposes a public HTTPS Streamable HTTP endpoint.
4. Product-to-MCP runs an MCP initialization and `tools/list` check.
5. Product-to-MCP checks that the endpoint returns the expected authorization
   challenge and metadata.
6. The customer enters their Smithery namespace, server name, and API key in a
   one-time publish form.
7. Product-to-MCP calls Smithery's release API and immediately discards the
   submitted Smithery API key.
8. Product-to-MCP shows the deployment status, warnings, MCP URL, and a manual
   publish command/payload as a recovery path.
9. Product-to-MCP stores the Smithery server identity and verification status,
   but not a permanent broad Smithery API key.
