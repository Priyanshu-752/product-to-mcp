# Repository Structure

```text
product-to-mcp/
├── backend/                 # FastAPI, compiler, gateway, and storage
├── frontend/                # React/Vite prototype interface
├── examples/                # Demo OpenAPI and upstream API
├── docs/                    # Protocol, architecture, inputs, readiness
├── architecture/            # Ownership and subsystem contracts
├── decisions/               # Durable architectural decisions
├── plans/                   # Active implementation plans
├── test_index/              # Validation commands and meaning
├── scripts/                 # Repeatable local commands
├── logs/                    # Dated implementation evidence
├── context_checkpoints/     # Restart handoffs
├── context_history/         # Archived contexts
├── knowledgebase/           # Verified reusable findings
├── audits/                  # Read-only audit records
├── errors/                  # Reusable failure evidence
└── skills/                  # Stable repeatable workflows only
```

Generated state belongs only in `.runtime/`, `.venv/`, `node_modules/`,
`dist/`, and local environment files.

