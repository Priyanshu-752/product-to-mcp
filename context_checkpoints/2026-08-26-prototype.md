# Prototype Checkpoint

The first Product-to-MCP vertical slice is implemented and locally validated.
Start with `critical_prompt.md`, `context.md`, and
`plans/2026-08-26-product-to-mcp-plan.md`.

Current working path:

```text
OpenAPI upload -> operation discovery -> read-only selection
-> immutable release -> MCP initialize/tools/list/tools/call
-> local upstream API response
```

Next work is browser E2E coverage and public HTTPS deployment, followed by the
PostgreSQL and Supabase connectors.

