# Product-to-MCP

Product-to-MCP is a managed platform that helps a product owner expose a safe,
versioned MCP server for their API or data source.

The first release supports:

- OpenAPI-based HTTP APIs;
- PostgreSQL databases;
- Supabase through its PostgREST/REST interface;
- read-only MCP tools by default;
- immutable releases served by a managed Streamable HTTP gateway;
- customer-owned Smithery publishing from the prototype UI.

## Prototype-first milestone

Before implementing the complete production architecture, we will build a
small working product that can be opened in the browser:

1. the user enters a project name, API base URL, and OpenAPI JSON/YAML;
2. the backend discovers supported read-only API operations;
3. the user selects the operations to expose;
4. the backend creates an immutable MCP manifest;
5. the generated MCP runs at a real Streamable HTTP endpoint;
6. the frontend can inspect and test its tools;
7. the endpoint is deployed publicly and published to Smithery.

The prototype uses one repository, one frontend, one FastAPI backend, SQLite,
and the official Python MCP SDK. PostgreSQL, Supabase, multi-tenant production
storage, workers, and advanced authorization follow after this end-to-end path
is working.

This repository currently contains the product research and implementation
plan. The documents are deliberately separated so the protocol, product
architecture, operational design, and execution plan remain easy to review.

## Documents

1. [MCP fundamentals](docs/01-mcp-fundamentals.md) — what MCP is and how a
   host, client, and server communicate.
2. [What an MCP builder needs](docs/02-what-is-needed-to-build-mcp.md) — the
   protocol, source adapters, security, runtime, and deployment requirements.
3. [Product architecture and flows](docs/03-product-architecture-and-flows.md)
   — the user journey, folder structure, backend flow, API shape, and Smithery
   publishing flow.
4. [Customer inputs and production readiness](docs/04-customer-inputs-and-production-readiness.md)
   — what customers provide, source-specific rules, risks, and readiness gates.
5. [Implementation plan](plans/2026-08-26-product-to-mcp-plan.md) — phases,
   deliverables, testing, and acceptance criteria.

## Core architectural decision

We will compile customer configuration into an immutable runtime manifest and
serve it from a hardened multi-tenant gateway. We will not execute customer
code or ask an LLM to generate executable server code in the production path.

The product owner supplies the upstream API/database connection. The generated
MCP is protected separately, and the upstream credential is kept server-side.
Therefore, owner-shared access must be clearly disclosed: authorized MCP users
operate against the data permissions of that owner connection.
