# Architecture Code Map

| Area | Owner | Responsibility | Main validation |
| --- | --- | --- | --- |
| Application host | `backend/src/product_to_mcp/main.py` | Compose FastAPI, store, secrets, gateway | health smoke |
| Control API | `backend/src/product_to_mcp/api/` | Project, source, release, publish routes | API tests |
| Domain | `backend/src/product_to_mcp/domain/` | Stable product models and errors | model tests |
| OpenAPI | `backend/src/product_to_mcp/openapi/` | Parse and discover supported operations | parser tests |
| Compiler | `backend/src/product_to_mcp/compiler/` | Selected operations to manifest tools | compiler tests |
| MCP gateway | `backend/src/product_to_mcp/gateway/` | JSON-RPC protocol and upstream execution | MCP smoke |
| Storage | `backend/src/product_to_mcp/storage/` | Prototype SQLite and secret references | persistence tests |
| Smithery | `backend/src/product_to_mcp/smithery/` | External release API integration | publisher tests |
| Frontend | `frontend/src/` | User-visible prototype workflow | typecheck/build |
| Demo | `examples/` | Safe local upstream and source example | HTTP smoke |

