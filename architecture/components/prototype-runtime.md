# Prototype Runtime Contract

The prototype runs one FastAPI process with two logical boundaries:

- control-plane routes under `/v1` mutate projects, sources, policies, and
  releases;
- data-plane routes under `/mcp/{deployment_slug}/mcp` serve the immutable
  release manifest and execute approved upstream calls.

SQLite stores product metadata and manifests. `PrototypeSecretStore` keeps
upstream secrets process-local and never serializes them. This is deliberately
not a production secret solution. The production replacement is an external
KMS/Vault-backed implementation behind the same conceptual port.

