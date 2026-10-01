"""Write the OpenAPI schema for TypeScript type generation (pnpm gen:api).

uv run python -m cornerpin.openapi apps/web/lib/api/openapi.json
"""

import json
import sys
from pathlib import Path

from cornerpin.main import create_app


def main() -> None:
    target = Path(sys.argv[1])
    schema = create_app().openapi()
    target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
