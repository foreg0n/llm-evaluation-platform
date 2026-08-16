from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.db.base import Base
from backend.db import models  # noqa: F401


def test_initial_schema_contains_all_domain_tables() -> None:
    assert set(Base.metadata.tables) == {
        "users",
        "projects",
        "datasets",
        "dataset_items",
        "variants",
        "evaluation_runs",
        "evaluation_run_variants",
        "evaluation_results",
    }


def test_database_has_exactly_one_migration_head() -> None:
    config = Config("alembic.ini")
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["20260815_0003"]
