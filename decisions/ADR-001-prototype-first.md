# ADR-001: Prototype-First MCP Runtime

## Decision

Start with one understandable FastAPI application, SQLite, a deterministic
OpenAPI compiler, and a minimal Streamable HTTP MCP handler. Build the complete
browser-to-Smithery path before adding PostgreSQL, Supabase, workers, or service
decomposition.

## Reason

The product risk is proving that a customer can provide an API and receive a
usable MCP. A visible vertical slice gives faster feedback on tool naming,
schemas, upstream execution, MCP compatibility, and Smithery publishing.

## Consequences

The prototype is not production-ready. It intentionally lacks external secret
storage, full OAuth, durable jobs, multi-tenant isolation, and horizontal
scaling. Those are documented follow-up work and must not be implied by the
prototype.

