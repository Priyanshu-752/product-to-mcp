# Test Index

## Backend

```powershell
python -m pytest backend/tests -q
```

Proves parser, compiler, storage, gateway, and control API behavior.

## Frontend

```powershell
npm --prefix frontend install
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Proves the browser prototype compiles with strict TypeScript checks.

## Local smoke

```powershell
$env:PYTHONPATH = "backend/src"
python -m uvicorn product_to_mcp.main:app --app-dir backend/src --port 8000
```

Then create a project, upload `examples/demo-openapi.yaml`, generate a release,
and call the MCP endpoint with JSON-RPC.

The prototype currently has no automated Smithery test because publishing
requires a customer-owned Smithery credential and a public HTTPS deployment.
