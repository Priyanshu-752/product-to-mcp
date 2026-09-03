import os
import sys
from pathlib import Path

os.environ.setdefault("PRODUCT_TO_MCP_SKIP_DOTENV", "1")

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
