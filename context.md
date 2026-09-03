# Current Context

Updated: 2026-08-26

## Current state

The repository contains the documented prototype design and a working first
vertical slice: OpenAPI upload, read-only operation selection, immutable
manifest creation, MCP tool execution, and Smithery publishing integration.

## Current implementation status

- Repository governance and documentation: present.
- FastAPI control API: implemented for projects, OpenAPI sources, operations,
  releases, MCP tests, and Smithery publishing.
- SQLite project/source/release storage: implemented.
- OpenAPI parser and operation discovery: implemented for the prototype.
- MCP JSON-RPC endpoint: implemented for initialize/tools/list/tools/call with
  the prototype-compatible Streamable HTTP handler.
- React workflow: implemented for project creation, upload, tool review,
  release creation, and local tool testing.
- Local demo API/OpenAPI: present.
- PostgreSQL/Supabase: planned after the OpenAPI vertical slice.
- Production authentication, external secrets, durable workers, and hardening:
  not complete.

## Validation evidence

- Backend tests: `3 passed`.
- Frontend strict typecheck and production build: passed.
- Real local HTTP smoke: backend `8000`, demo API `9000`; imported the demo
  OpenAPI file, created a release, initialized MCP, listed tools, and called
  `getproduct` successfully.
- In-app browser visual verification was unavailable because no browser surface
  was connected; frontend build/typecheck is the available UI validation.

## Next step

Add a browser end-to-end test and public HTTPS deployment. PostgreSQL,
Supabase, OAuth, external secret storage, and production workers remain future
work.
