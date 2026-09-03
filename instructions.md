# Repository Instructions

- This repository is authoritative for the Product-to-MCP prototype.
- Keep implementation, tests, architecture notes, and user-facing behavior in
  this repository.
- Do not copy unrelated `saastoagent` application state or RouteDeck behavior
  into this project.
- Use `apply_patch` for source and documentation edits.
- Preserve explicit source ownership: OpenAPI parsing belongs to `openapi`,
  compilation belongs to `compiler`, MCP protocol handling belongs to `gateway`,
  and HTTP routes belong to `api`.
- Do not store real credentials in source, fixtures, logs, screenshots, or
  documentation.
- Every new behavior needs a focused test and a documentation anchor.
- Prototype limitations must be written down rather than hidden.
- Do not claim production readiness until the gates in
  `docs/04-customer-inputs-and-production-readiness.md` pass.

