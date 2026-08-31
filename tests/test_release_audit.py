import json

from backend.dataset_import import parse_dataset_file
from scripts.release_audit import ROOT, audit_repository, migration_graph


def test_portfolio_benchmark_is_a_valid_importable_dataset() -> None:
    path = ROOT / "examples" / "portfolio-benchmark.json"
    parsed = parse_dataset_file(path.name, path.read_bytes())

    assert parsed.name == "Evalflow Portfolio Benchmark"
    assert len(parsed.items) == 15
    assert len({item.external_id for item in parsed.items}) == 15
    assert all(item.expected_output for item in parsed.items)
    assert all(item.keywords for item in parsed.items)

    document = json.loads(path.read_text(encoding="utf-8"))
    assert "fake" not in document["description"].lower()


def test_alembic_migration_graph_has_one_complete_head() -> None:
    heads, missing_parents = migration_graph(ROOT)

    assert heads == {"20260830_0007"}
    assert missing_parents == set()


def test_repository_passes_release_audit() -> None:
    report = audit_repository(ROOT)

    assert report.errors == []
    assert len(report.checks) == 5
