import time
from collections.abc import Callable

from evals.metrics import calculate_metrics
from evals.models import DatasetItem, EvaluationResult, Variant, VariantSummary
from evals.providers import generate

GenerateFunction = Callable[[str, Variant], str]


def run_evaluation(
    dataset: list[DatasetItem],
    variants: list[Variant],
    generate_function: GenerateFunction = generate,
) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []

    for item in dataset:
        for variant in variants:
            started_at = time.perf_counter()

            try:
                output = generate_function(item.input, variant)
                latency_ms = (time.perf_counter() - started_at) * 1000
                metrics = calculate_metrics(
                    output=output,
                    expected=item.expected_output,
                    keywords=item.keywords,
                )
                result = EvaluationResult(
                    item_id=item.id,
                    variant_name=variant.name,
                    model=variant.model,
                    provider=variant.provider,
                    input=item.input,
                    expected_output=item.expected_output,
                    output=output,
                    latency_ms=latency_ms,
                    metrics=metrics,
                )
            except Exception as exc:
                latency_ms = (time.perf_counter() - started_at) * 1000
                result = EvaluationResult(
                    item_id=item.id,
                    variant_name=variant.name,
                    model=variant.model,
                    provider=variant.provider,
                    input=item.input,
                    expected_output=item.expected_output,
                    output=None,
                    latency_ms=latency_ms,
                    metrics=None,
                    error=f"{type(exc).__name__}: {exc}",
                )

            results.append(result)

    return results


def summarize_results(
    results: list[EvaluationResult],
    variants: list[Variant],
) -> list[VariantSummary]:
    summaries: list[VariantSummary] = []

    for variant in variants:
        variant_results = [
            result for result in results if result.variant_name == variant.name
        ]
        successful = [
            result for result in variant_results if result.metrics is not None
        ]

        def average(metric_name: str) -> float:
            if not successful:
                return 0.0
            values = [
                getattr(result.metrics, metric_name)
                for result in successful
                if result.metrics is not None
            ]
            return sum(values) / len(values)

        average_quality = (
            sum(result.metrics.quality for result in successful if result.metrics)
            / len(successful)
            if successful
            else 0.0
        )
        average_latency = (
            sum(result.latency_ms for result in variant_results)
            / len(variant_results)
            if variant_results
            else 0.0
        )

        summaries.append(
            VariantSummary(
                variant_name=variant.name,
                average_exact_match=average("exact_match"),
                average_normalized_exact_match=average(
                    "normalized_exact_match"
                ),
                average_keyword_score=average("keyword_score"),
                average_quality=average_quality,
                average_latency_ms=average_latency,
                error_count=sum(
                    result.error is not None for result in variant_results
                ),
            )
        )

    return summaries

