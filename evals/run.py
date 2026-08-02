import json
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from evals.dataset import load_dataset
from evals.models import EvaluationReport, Variant, VariantSummary
from evals.runner import run_evaluation, summarize_results

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET_PATH = PROJECT_ROOT / "evals" / "datasets" / "questions.jsonl"
DEFAULT_ARTIFACT_PATH = PROJECT_ROOT / "artifacts" / "results.json"

VARIANTS = [
    Variant(name="fake_qwen", model="fake_qwen"),
    Variant(name="fake_llama", model="fake_llama"),
]


def build_table(summaries: list[VariantSummary]) -> Table:
    table = Table(title="LLM Evaluation Summary")
    table.add_column("Variant", style="cyan")
    table.add_column("Quality", justify="right")
    table.add_column("Exact", justify="right")
    table.add_column("Normalized", justify="right")
    table.add_column("Keywords", justify="right")
    table.add_column("Latency, ms", justify="right")
    table.add_column("Errors", justify="right")

    for summary in summaries:
        table.add_row(
            summary.variant_name,
            f"{summary.average_quality:.2f}",
            f"{summary.average_exact_match:.2f}",
            f"{summary.average_normalized_exact_match:.2f}",
            f"{summary.average_keyword_score:.2f}",
            f"{summary.average_latency_ms:.3f}",
            str(summary.error_count),
        )

    return table


def save_report(report: EvaluationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    dataset = load_dataset(DEFAULT_DATASET_PATH)
    results = run_evaluation(dataset, VARIANTS)
    summaries = summarize_results(results, VARIANTS)
    run_id = datetime.now(UTC).isoformat(timespec="seconds")

    report = EvaluationReport(
        run_id=run_id,
        dataset=str(DEFAULT_DATASET_PATH.relative_to(PROJECT_ROOT)),
        variants=VARIANTS,
        summary=summaries,
        results=results,
    )
    save_report(report, DEFAULT_ARTIFACT_PATH)

    console = Console()
    console.print(build_table(summaries))
    console.print(f"\nReport saved to: [green]{DEFAULT_ARTIFACT_PATH}[/green]")


if __name__ == "__main__":
    main()
