# Customer Inputs and Production Readiness

## What every customer must provide

Every project needs:

- product/project name;
- short description and intended users;
- data ownership and privacy classification;
- desired MCP server name;
- expected caller audience;
- allowed regions and retention requirements;
- support contact and incident contact;
- tools that must not be exposed;
- whether data may contain personal, financial, health, or confidential data.

## OpenAPI customer checklist

The customer provides:

- OpenAPI 3.0/3.1 JSON or YAML;
- public API base URL or approved private-network route;
- API version/environment;
- authentication type: API key, bearer token, OAuth, or another supported
  mechanism;
- credentials through the secure setup form;
- operation descriptions and business meaning where the specification is
  unclear;
- operations to expose;
- fields that must be redacted;
- expected rate limits and timeout requirements;
- sample non-sensitive responses for validation, if needed.

The customer must confirm that the credential permits the selected operations.
The platform must not infer permission from an OpenAPI document alone.

## PostgreSQL customer checklist

The customer provides:

- host, port, database, and TLS configuration;
- a dedicated read-only role;
- username and password through the secure setup form;
- approved schemas and tables;
- approved columns;
- allowed filters and sort fields;
- maximum result size;
- data classification and field redaction rules;
- whether views are preferred over base tables;
- expected network access method, such as private networking.

The customer should not provide an administrator credential. The platform must
verify that the role cannot perform writes before activating a read-only
release.

## Supabase customer checklist

The customer provides:

- Supabase project URL;
- selected project/environment;
- anon/public key or another explicitly supported key mode;
- approved tables, views, or RPCs;
- Row Level Security policy expectations;
- approved columns, filters, and limits;
- fields that must be redacted;
- whether the data is intended for owner-shared access.

The Supabase `service_role` key is highly sensitive and bypasses normal Row
Level Security. It must not be the default setup and must never be exposed to
the browser, MCP client, model, logs, or release manifest.

## What the customer does not provide

The customer should not upload:

- raw production database backups;
- private keys in the OpenAPI document;
- credentials in descriptions or tool names;
- unrestricted administrator database accounts;
- arbitrary executable code;
- secrets in screenshots, support tickets, or sample payloads.

## Production-readiness gates

### Security

- Tenant isolation is enforced in every control-plane query and gateway lookup.
- All credentials are encrypted, write-only, versioned, rotatable, and scoped.
- MCP caller tokens are separate from upstream credentials.
- OAuth audience and scope validation is implemented.
- Imported descriptions and schemas are treated as untrusted input.
- SSRF, DNS rebinding, unsafe redirects, private-network access, and oversized
  responses are blocked.
- Secrets and personal data are redacted from logs and traces.

### Correctness

- Every active release is immutable and hash-addressed.
- Only reviewed tools appear in `tools/list`.
- Tool arguments are validated before upstream execution.
- Database identifiers come only from approved manifests.
- No unrestricted SQL exists in the default database connector.
- Upstream calls have deterministic timeout and retry rules.
- Response schemas and truncation behavior are documented.

### Reliability

- Control-plane jobs are durable and retryable.
- Gateway instances can restart without losing release truth.
- Release deployment and rollback are explicit operations.
- Health, readiness, latency, errors, upstream status, and quota usage are
  observable.
- Database and object-storage backups are tested.

### Abuse and cost control

- Per-customer quotas and rate limits exist.
- Tool calls have maximum execution duration and response size.
- Repeated failing calls are throttled.
- Customer ownership and acceptable-use policies are recorded.
- Public server discovery and abuse reports have an operational owner.

### Smithery compatibility

- The endpoint is public HTTPS and reachable by the Smithery scanner.
- Streamable HTTP is implemented correctly.
- `initialize` and `tools/list` are stable and deterministic.
- Protected endpoints return the correct authorization challenge.
- The customer can publish in their own namespace from the product UI, and can
  use a generated manual command/payload if automated publishing fails.
- The published server URL and release hash are recorded for support.

## What we will build first

### v1

- multi-tenant project and source control plane;
- OpenAPI 3.0/3.1 adapter;
- PostgreSQL read-only adapter;
- Supabase PostgREST read-only adapter;
- secure connection setup and tests;
- operation/table/field curation;
- immutable manifest compiler;
- Streamable HTTP MCP gateway;
- OAuth-protected MCP access;
- redacted audit logging;
- Smithery publish-readiness and one-time API publishing.

### After v1

- reviewed writes with confirmation and idempotency controls;
- per-end-user upstream OAuth delegation;
- direct Supabase PostgreSQL mode with carefully documented RLS behavior;
- resources and prompts;
- event/trigger support;
- customer-hosted exports;
- persistent Smithery account connection and automated republishing;
- broader database engines and private networking options.
