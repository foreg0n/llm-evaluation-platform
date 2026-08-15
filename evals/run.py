import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from evals.dataset import load_dataset
from evals.models import EvaluationReport, Variant, VariantSummary
from evals.runner import run_evaluation, summarize_results

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET_PATH = PROJECT_ROOT / "evals" / "datasets" / "questions.jsonl"
DEFAULT_ARTIFACT_PATH = PROJECT_ROOT / "artifacts" / "results.json"
DEFAULT_GROQ_MODELS = (
    "groq/qwen/qwen3.6-27b",
    "groq/openai/gpt-oss-20b",
)


def positive_int(value: str) -> int:
    parsed_value = int(value)
    if parsed_value < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed_value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Groq-hosted models against a JSONL dataset."
    )
    parser.add_argument(
        "--model",
        dest="models",
        action="append",
        help=(
            "Groq model identifier. Repeat this option to compare multiple "
            "models. Defaults to Qwen 3.6 27B and GPT-OSS 20B."
        ),
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=500)
    parser.add_argument("--system-prompt")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument(
        "--concurrency",
        type=positive_int,
        default=3,
        help="Maximum number of concurrent model requests (default: 3).",
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_ARTIFACT_PATH)
    return parser.parse_args(argv)


def build_variants(args: argparse.Namespace) -> list[Variant]:
    if not os.getenv("GROQ_API_KEY"):
        raise ValueError(
            "GROQ_API_KEY is not set. Create a key at "
            "https://console.groq.com/keys and add it to .env"
        )

    models = args.models or DEFAULT_GROQ_MODELS
    variants: list[Variant] = []

    for model in models:
        normalized_model = (
            model if model.startswith("groq/") else f"groq/{model}"
        )
        variants.append(
            Variant(
                name=normalized_model.removeprefix("groq/"),
                model=normalized_model,
                provider="litellm",
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                system_prompt=args.system_prompt,
                timeout_seconds=args.timeout,
                max_retries=args.max_retries,
            )
        )

    return variants


def build_table(summaries: list[VariantSummary]) -> Table:
    table = Table(title="LLM Evaluation Summary")
    table.add_column("Variant", style="cyan")
    table.add_column("Quality", justify="right")
    table.add_column("Latency, ms", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost, USD", justify="right")
    table.add_column("Retries", justify="right")
    table.add_column("Errors", justify="right")

    for summary in summaries:
        table.add_row(
            summary.variant_name,
            f"{summary.average_quality:.2f}",
            f"{summary.average_latency_ms:.3f}",
            str(summary.total_tokens),
            f"{summary.total_estimated_cost:.6f}",
            str(summary.total_retries),
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


async def async_main(argv: Sequence[str] | None = None) -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    args = parse_args(argv)
    try:
        variants = build_variants(args)
    except ValueError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc
    dataset_path = args.dataset.resolve()
    output_path = args.output.resolve()

    dataset = load_dataset(dataset_path)
    results = await run_evaluation(
        dataset,
        variants,
        concurrency=args.concurrency,
    )
    summaries = summarize_results(results, variants)
    run_id = datetime.now(UTC).isoformat(timespec="seconds")

    report = EvaluationReport(
        run_id=run_id,
        dataset=str(dataset_path),
        variants=variants,
        summary=summaries,
        results=results,
    )
    save_report(report, output_path)

    console = Console()
    console.print(build_table(summaries))
    console.print(f"\nReport saved to: [green]{output_path}[/green]")


def main(argv: Sequence[str] | None = None) -> None:
    asyncio.run(async_main(argv))


if __name__ == "__main__":
    main()
