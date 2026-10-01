"""The ORM models must describe the tables the migrations create. Columns, types and nullability
are compared; indexes, constraints, policies and triggers belong to the migrations alone."""

from typing import cast

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from cornerpin.listings.models import Base

from .conftest import Databases

COMPARED = {"add_column", "remove_column", "modify_type", "modify_nullable", "add_table"}


def _kind(diff: object) -> str:
    # Column-level diffs arrive as a list of tuples; table-level ones as a single tuple.
    entry = cast("list[object]", diff)[0] if isinstance(diff, list) else diff
    return str(cast("tuple[object, ...]", entry)[0])


def _only_model_tables(name: str | None, kind: str, _parent: object) -> bool:
    return kind != "table" or name in Base.metadata.tables


def test_listings_models_match_the_database(db: Databases) -> None:
    with db.owner.connect() as conn:
        context = MigrationContext.configure(
            conn, opts={"compare_type": True, "include_name": _only_model_tables}
        )
        diffs = [d for d in compare_metadata(context, Base.metadata) if _kind(d) in COMPARED]
    assert diffs == []
