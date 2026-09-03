# MCP Fundamentals

## What MCP is

The Model Context Protocol (MCP) is a standard way for an AI application to
connect to external capabilities. It defines a common protocol between:

- a **host** — the application containing the model and user experience;
- an **MCP client** — a connection managed by the host for one MCP server;
- an **MCP server** — a service exposing tools, resources, and prompts.

The protocol uses JSON-RPC messages and capability negotiation. The host can
run multiple isolated clients, normally one client per connected server. The
server announces what it supports, and the client uses only the capabilities
that were negotiated.

Official references:

- [MCP architecture](https://modelcontextprotocol.io/specification/2025-06-18/architecture)
- [MCP server features](https://modelcontextprotocol.io/specification/2025-06-18/server/index)
- [MCP transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)

## The three MCP primitives

### Tools

Tools are executable functions. They are the primary primitive for turning an
API endpoint or database operation into an MCP capability.

Examples:

- `list_products`
- `get_order`
- `search_customers`

A tool normally contains a name, description, input JSON Schema, and a result.
The model may propose a tool call, but the host should control consent and the
server must validate the request again.

### Resources

Resources are data or context identified by a URI. They are better suited to
documents, files, reports, schemas, or stable contextual data than to arbitrary
side-effecting actions.

Examples:

- `product://catalog/schema`
- `report://monthly-sales/2026-08`

Resources may be static or dynamically generated through URI templates.

### Prompts

Prompts are reusable templates that help a user start a particular interaction.
They are user-controlled rather than ordinary model-selected actions.

Examples:

- `summarize_customer_history`
- `prepare_order_review`

Product-to-MCP will initially generate tools only. Automatic prompts and
resources will be added after the tool contract is stable.

## How a normal MCP session works

```text
User / model
    -> Host application
        -> MCP client
            -> initialize / capability negotiation
            -> tools/list
            -> tools/call
                -> MCP server validates the call
                -> MCP server performs an allowed operation
                -> MCP server returns structured content
```

The important point is that the MCP server is not the model. It does not need
to understand natural language. It exposes clear capabilities; the host/model
decides when to use them under the host's consent policy.

## Transport choices

### Streamable HTTP

Streamable HTTP is the remote-server transport we will use for hosted MCPs. A
server exposes one endpoint, such as:

```text
https://mcp.example.com/mcp/acme-store/release-abc/mcp
```

The endpoint supports HTTP POST for JSON-RPC messages and may support GET/SSE
for server-to-client streaming and notifications. It is the right choice for
Smithery and other remote MCP clients.

### stdio

With stdio, an MCP client starts the MCP server as a local child process. The
server reads messages from stdin and writes only valid MCP messages to stdout.
This is useful for local desktop tools but is not the primary hosting model for
Product-to-MCP.

## Authentication and authorization

MCP authorization is optional at the protocol level, but a public hosted
server must normally be protected. A production HTTP server should:

- return `401` when authentication is missing or invalid;
- return `403` when the caller lacks a required scope;
- expose OAuth protected-resource metadata;
- validate that tokens are intended for this exact MCP server;
- never forward an inbound MCP token to the upstream API;
- use a separate server-side credential for the customer’s API/database.

The MCP authorization specification is based on OAuth 2.1, protected-resource
metadata, authorization-server metadata, and resource indicators. See the
[official authorization specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization).

## What MCP does not provide automatically

MCP does not automatically provide:

- a database driver;
- API authentication to a third-party service;
- tenant isolation;
- rate limiting;
- secret storage;
- retry and timeout policy;
- audit logs;
- safe write approvals;
- protection from prompt injection or malicious tool descriptions;
- deployment, TLS, monitoring, or billing.

Those are application responsibilities. Product-to-MCP must implement them
around the protocol runtime.

## A simple tool example

An imported API operation might become:

```json
{
  "name": "list_products",
  "description": "List products from the product catalog.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "limit": { "type": "integer", "minimum": 1, "maximum": 100 }
    }
  }
}
```

The runtime manifest separately stores that this tool maps to `GET /products`.
The mapping contains a credential reference, not the actual API key.

