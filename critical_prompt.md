# Product-to-MCP Critical Prompt

## North star

Product-to-MCP helps a product owner expose a safe, understandable, versioned
MCP server for an approved API or data source.

The first product proof is simple: a user provides an OpenAPI definition, the
system discovers read-only operations, the user selects tools, and the system
serves and publishes a working MCP server.

## Non-negotiable boundaries

- The user must explicitly select the capabilities exposed by an MCP release.
- A source document never grants permission by itself.
- Prototype releases expose read-only GET/HEAD operations only.
- The MCP runtime may execute only operations present in the immutable release
  manifest.
- Callers cannot choose arbitrary URLs, headers, credentials, SQL, or releases.
- Secrets never appear in tool schemas, manifests, logs, browser state, or
  responses.
- Imported descriptions and schemas are untrusted input.
- No customer code or LLM-generated executable code runs in the platform.
- Failures remain visible failures; no silent mock or fallback may look
  successful.
- Prototype shortcuts must be clearly marked and replaced before production.
- Each new source revision creates a new release; active releases are never
  mutated in place.

## Scope

Prototype: OpenAPI 3.0/3.1, one FastAPI application, SQLite, read-only tools,
local demo API, public deployment, and Smithery publishing.

Next: PostgreSQL and Supabase PostgREST connectors, external secret storage,
durable workers, OAuth, multi-tenant production persistence, and observability.

