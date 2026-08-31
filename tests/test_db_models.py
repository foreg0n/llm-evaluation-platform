from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.db import models  # noqa: F401
from backend.db.base import Base


def test_initial_schema_contains_all_domain_tables() -> None:
    assert set(Base.metadata.tables) == {
        "users",
        "refresh_sessions",
        "account_action_tokens",
        "provider_credentials",
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

    assert scripts.get_heads() == ["20260830_0007"]


def test_evaluation_results_have_pagination_indexes() -> None:
    index_names = {
        index.name for index in Base.metadata.tables["evaluation_results"].indexes
    }

    assert "ix_evaluation_results_run_dataset_item_variant" in index_names
    assert "ix_evaluation_results_run_variant" in index_names
