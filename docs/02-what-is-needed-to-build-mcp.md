# What Is Needed to Build an MCP

## Minimum technical pieces

A working MCP server needs five layers:

1. **Protocol runtime** — an official MCP SDK or equivalent implementation.
2. **Capability registry** — declared tools, and later resources/prompts.
3. **Execution adapter** — logic that maps a tool call to an API or database
   operation.
4. **Security boundary** — caller authentication, authorization, secret
   handling, validation, and isolation.
5. **Deployment runtime** — HTTPS, health checks, scaling, logs, metrics, and
   release management.

For Product-to-MCP, the MCP SDK or protocol handler should be treated as a
protocol component. It must not own business policy, customer configuration, or
secret storage. The current prototype uses a deliberately small compatible
handler; official SDK compatibility testing is a production gate.

## API-to-MCP requirements

For an OpenAPI source, the builder needs:

- an OpenAPI 3.0 or 3.1 JSON/YAML document;
- an upstream base URL or a valid `servers` entry;
- operation IDs or deterministic operation-name generation;
- parameter and request-body schemas;
- response schemas when available;
- supported authentication configuration;
- an owner-selected operation allowlist;
- descriptions that are safe to show to an AI client.

The compiler must transform an operation into a tool definition without
changing its meaning. It must preserve required fields, enums, formats,
constraints, and response shape where possible.

The compiler must reject or quarantine operations that are ambiguous,
unsupported, unsafe, or impossible to validate. It must never expose every
operation simply because it appeared in the uploaded document.

## Database-to-MCP requirements

Databases require more policy than APIs because a generic SQL tool can expose
the entire database or become an arbitrary code-execution path through unsafe
queries.

The first database implementation should expose curated, read-only tools such
as:

- `orders_list`
- `orders_get`
- `orders_search`
- `customers_list`

Each generated tool must have:

- a selected schema and table;
- selected columns;
- explicit filter and sort fields;
- a maximum row count;
- a maximum response size;
- a timeout;
- an optional field denylist for secrets and personal data;
- a database credential reference;
- an audit policy.

The v1 database connector must not expose unrestricted SQL, arbitrary joins,
DDL, stored-procedure execution, or writes.

## PostgreSQL support

The PostgreSQL adapter should use a dedicated least-privilege database role,
TLS, connection pooling, and a read-only transaction policy. Schema discovery
must use metadata queries and must not modify the database.

The owner selects the schemas, tables, columns, and supported query patterns.
The compiler creates a manifest of those exact capabilities. Runtime SQL is
parameterized; identifiers come only from the approved manifest.

## Supabase support

Supabase is PostgreSQL plus managed services such as PostgREST, authentication,
storage, and realtime. Product-to-MCP should initially support Supabase through
the PostgREST/REST API so Row Level Security remains part of the request path.

The owner provides:

- the Supabase project URL;
- the selected API key mode;
- the allowed tables/views or RPCs;
- the intended Row Level Security policy;
- the selected columns and filters.

The `service_role` key must never be placed in browser code, MCP tool schemas,
logs, or customer-visible responses. Because it can bypass Row Level Security,
it should not be the default v1 credential. If direct PostgreSQL access is
later added for Supabase, it must use a separate restricted database role and
must document whether RLS is enforced or bypassed.

## Credentials

Credentials must be stored in a dedicated secret manager or encrypted vault.
The application stores only:

- credential reference ID;
- credential type;
- owner/project identity;
- allowed use and source binding;
- version and rotation metadata.

Credential values must never be stored in:

- OpenAPI documents after ingestion;
- release manifests;
- frontend state;
- MCP tool schemas;
- audit logs;
- error messages;
- model prompts;
- screenshots or test fixtures.

## Runtime safety

Every tool call needs:

1. caller authentication;
2. tenant and deployment resolution;
3. tool allowlist validation;
4. JSON Schema argument validation;
5. policy validation;
6. credential lookup;
7. safe upstream request construction;
8. timeout and response-size enforcement;
9. response redaction and normalization;
10. an audit record.

Outbound HTTP must protect against SSRF, DNS rebinding, unsafe redirects,
private-network access, metadata-service access, unsupported protocols, and
unbounded response bodies.

## Production deployment requirements

A production hosted MCP needs:

- public HTTPS and valid certificates;
- a stable `/mcp` endpoint;
- origin validation;
- OAuth discovery and token validation;
- stateless or externally coordinated session handling;
- horizontal scaling;
- health and readiness checks;
- structured logs with redaction;
- metrics for calls, failures, latency, and upstream status;
- per-tenant rate limits and quotas;
- release rollback;
- database backups and migration policy;
- secret rotation and revocation;
- abuse detection and cost controls;
- incident response and data-retention rules.

## Smithery requirements

Smithery can publish an existing public HTTPS Streamable HTTP endpoint and
proxy it through its gateway. The endpoint must be reachable by Smithery’s
scanner. If authentication is required, it must be compatible with Smithery’s
supported configuration/authentication flow.

Product-to-MCP will validate the endpoint and let the customer publish it from
the prototype UI using their Smithery namespace and a one-time Smithery API
key. The backend calls Smithery's release API and does not persist that key.
The UI also exposes the exact publish command/payload as a recovery path. See
[Smithery publish documentation](https://smithery.ai/docs/build/publish).
