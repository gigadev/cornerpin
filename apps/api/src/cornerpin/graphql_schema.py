"""Write the public GraphQL schema (SDL) for TypeScript codegen (pnpm gen:api).

uv run python -m cornerpin.graphql_schema apps/web/lib/graphql/schema.graphql
"""

import sys
from pathlib import Path

from cornerpin.listings.public_graphql import schema


def main() -> None:
    Path(sys.argv[1]).write_text(schema.as_str() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
