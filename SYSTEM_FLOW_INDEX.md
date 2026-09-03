# System Flow Index

## Prototype flow

`frontend/src/App.tsx`
  -> `backend/src/product_to_mcp/api/routes.py`
  -> `openapi/parser.py`
  -> `openapi/operations.py`
  -> `compiler/manifest.py`
  -> `storage/sqlite.py`
  -> `gateway/server.py`
  -> `gateway/executor.py`
  -> customer upstream API

Smithery publishing enters through the release route and is owned by
`smithery/publisher.py`.

