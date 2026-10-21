"""Writes the OpenAPI schema used to generate the TypeScript client.

Run: python -m app.scripts.export_openapi ../packages/api-client/openapi.json
"""

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
