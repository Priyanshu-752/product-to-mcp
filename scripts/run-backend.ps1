$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "backend/src"
python -m uvicorn product_to_mcp.main:app --app-dir backend/src --host 127.0.0.1 --port 8000

