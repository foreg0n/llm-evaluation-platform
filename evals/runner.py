import asyncio
import time
from collections.abc import Awaitable, Callable

from evals.metrics import calculate_metrics
from evals.models import (
    DatasetItem,
    EvaluationResult,
    GenerationResponse,
    Variant,
    VariantSummary,
)
from evals.providers import generate

GenerateFunction = Callable[
    [str, Variant],
    Awaitable[GenerationResponse | str],
]
ResultCallback = Callable[[EvaluationResult], Awaitable[None]]


async def _evaluate_one(
    item: DatasetItem,
    variant: Variant,
    generate_function: GenerateFunction,
    semaphore: asyncio.Semaphore,
) -> EvaluationResult:
    async with semaphore:
        started_at = time.perf_counter()

        try:
            generation = await generate_function(item.input, variant)
            if isinstance(generation, str):
                generation = GenerationResponse(output=generation)
            latency_ms = (time.perf_counter() - started_at) * 1000
            metrics = calculate_metrics(
                output=generation.output,
                expected=item.expected_output,
                keywords=item.keywords,
            )
            return EvaluationResult(
                item_id=item.id,
                variant_name=variant.name,
                model=variant.model,
                provider=variant.provider,
                input=item.input,
                expected_output=item.expected_output,
                output=generation.output,
                latency_ms=latency_ms,
                input_tokens=generation.input_tokens,
                output_tokens=generation.output_tokens,
                total_tokens=generation.total_tokens,
                estimated_cost=generation.estimated_cost,
                retry_count=generation.retry_count,
                metrics=metrics,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started_at) * 1000
            return EvaluationResult(
                item_id=item.id,
                variant_name=variant.name,
                model=variant.model,
                provider=variant.provider,
                input=item.input,
                expected_output=item.expected_output,
                output=None,
                latency_ms=latency_ms,
                retry_count=getattr(exc, "retry_count", 0),
                metrics=None,
                error=f"{type(exc).__name__}: {exc}",
            )


async def run_evaluation(
    dataset: list[DatasetItem],
    variants: list[Variant],
    generate_function: GenerateFunction = generate,
    concurrency: int = 3,
    on_result: ResultCallback | None = None,
    skip_pairs: set[tuple[str, str]] | None = None,
) -> list[EvaluationResult]:
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")

    semaphore = asyncio.Semaphore(concurrency)
    skipped = skip_pairs or set()
    indexed_inputs = [
        (item, variant)
        for item in dataset
        for variant in variants
        if (item.id, variant.name) not in skipped
    ]

    async def evaluate_indexed(
        index: int, item: DatasetItem, variant: Variant
    ) -> tuple[int, EvaluationResult]:
        result = await _evaluate_one(
            item, variant, generate_function, semaphore
        )
        return index, result

    tasks = [
        asyncio.create_task(evaluate_indexed(index, item, variant))
        for index, (item, variant) in enumerate(indexed_inputs)
    ]
    ordered_results: list[EvaluationResult | None] = [None] * len(tasks)

    try:
        for completed_task in asyncio.as_completed(tasks):
            index, result = await completed_task
            ordered_results[index] = result
            if on_result is not None:
                await on_result(result)
    finally:
        unfinished = [task for task in tasks if not task.done()]
        for task in unfinished:
            task.cancel()
        if unfinished:
            await asyncio.gather(*unfinished, return_exceptions=True)

    return [result for result in ordered_results if result is not None]


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
        total_input_tokens = sum(
            result.input_tokens or 0 for result in variant_results
        )
        total_output_tokens = sum(
            result.output_tokens or 0 for result in variant_results
        )
        total_tokens = sum(result.total_tokens or 0 for result in variant_results)
        total_estimated_cost = sum(
            result.estimated_cost or 0.0 for result in variant_results
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
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
                total_tokens=total_tokens,
                total_estimated_cost=total_estimated_cost,
                total_retries=sum(
                    result.retry_count for result in variant_results
                ),
                error_count=sum(
                    result.error is not None for result in variant_results
                ),
            )
        )

    return summaries

