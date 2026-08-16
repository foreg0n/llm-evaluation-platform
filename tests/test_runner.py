import asyncio

import pytest

from evals.models import DatasetItem, GenerationResponse, Variant
from evals.providers import ProviderExecutionError
from evals.runner import run_evaluation, summarize_results


def test_runner_keeps_successful_result() -> None:
    dataset = [
        DatasetItem(
            id="1",
            input="What is 5 + 7?",
            expected_output="12",
            keywords=["12"],
        )
    ]
    variants = [Variant(name="test", model="test")]

    async def generate(prompt: str, variant: Variant) -> str:
        return "12"

    results = asyncio.run(run_evaluation(dataset, variants, generate))

    assert len(results) == 1
    assert results[0].error is None
    assert results[0].metrics is not None
    assert results[0].metrics.quality == 1.0


def test_runner_isolates_provider_error() -> None:
    dataset = [
        DatasetItem(
            id="1",
            input="Question",
            expected_output="Answer",
        )
    ]
    variants = [Variant(name="broken", model="broken")]

    async def broken_provider(prompt: str, variant: Variant) -> str:
        raise TimeoutError("provider timeout")

    results = asyncio.run(
        run_evaluation(dataset, variants, broken_provider)
    )

    assert len(results) == 1
    assert results[0].output is None
    assert "TimeoutError" in (results[0].error or "")


def test_runner_continues_after_one_provider_error() -> None:
    dataset = [
        DatasetItem(id="1", input="Fail", expected_output="Answer"),
        DatasetItem(id="2", input="Succeed", expected_output="Answer"),
    ]
    variants = [Variant(name="real", model="real")]

    async def sometimes_fails(
        prompt: str,
        variant: Variant,
    ) -> GenerationResponse:
        if prompt == "Fail":
            raise ProviderExecutionError("TimeoutError: timeout", retry_count=2)
        return GenerationResponse(output="Answer")

    results = asyncio.run(
        run_evaluation(dataset, variants, sometimes_fails)
    )

    assert len(results) == 2
    assert results[0].error is not None
    assert results[0].retry_count == 2
    assert results[1].error is None
    assert results[1].output == "Answer"


def test_runner_saves_usage_cost_and_retries() -> None:
    dataset = [
        DatasetItem(
            id="1",
            input="Question",
            expected_output="Answer",
            keywords=["answer"],
        )
    ]
    variants = [Variant(name="real", model="real")]

    async def generate(
        prompt: str,
        variant: Variant,
    ) -> GenerationResponse:
        return GenerationResponse(
            output="Answer",
            input_tokens=8,
            output_tokens=2,
            total_tokens=10,
            estimated_cost=0.001,
            retry_count=1,
        )

    results = asyncio.run(
        run_evaluation(dataset, variants, generate)
    )
    summary = summarize_results(results, variants)

    assert results[0].total_tokens == 10
    assert results[0].estimated_cost == pytest.approx(0.001)
    assert results[0].retry_count == 1
    assert summary[0].total_tokens == 10
    assert summary[0].total_estimated_cost == pytest.approx(0.001)
    assert summary[0].total_retries == 1


def test_summary_aggregates_results() -> None:
    dataset = [
        DatasetItem(
            id="1",
            input="Question",
            expected_output="Answer",
            keywords=["answer"],
        )
    ]
    variants = [Variant(name="test", model="test")]

    async def generate(prompt: str, variant: Variant) -> str:
        return "Answer"

    results = asyncio.run(
        run_evaluation(dataset, variants, generate)
    )

    summary = summarize_results(results, variants)

    assert summary[0].average_quality == 1.0
    assert summary[0].error_count == 0


def test_runner_limits_concurrency() -> None:
    dataset = [
        DatasetItem(
            id=str(index),
            input=f"Question {index}",
            expected_output="Answer",
        )
        for index in range(6)
    ]
    variants = [Variant(name="test", model="test")]
    active_requests = 0
    maximum_active_requests = 0

    async def tracked_provider(
        prompt: str,
        variant: Variant,
    ) -> str:
        nonlocal active_requests, maximum_active_requests
        active_requests += 1
        maximum_active_requests = max(
            maximum_active_requests,
            active_requests,
        )
        await asyncio.sleep(0.01)
        active_requests -= 1
        return "Answer"

    results = asyncio.run(
        run_evaluation(
            dataset,
            variants,
            tracked_provider,
            concurrency=2,
        )
    )

    assert len(results) == 6
    assert maximum_active_requests == 2


def test_runner_rejects_invalid_concurrency() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        asyncio.run(run_evaluation([], [], concurrency=0))


def test_runner_reports_results_as_they_complete() -> None:
    dataset = [
        DatasetItem(id="1", input="Question", expected_output="Answer")
    ]
    variants = [Variant(name="test", model="test")]
    reported = []

    async def generate(prompt: str, variant: Variant) -> str:
        return "Answer"

    async def on_result(result) -> None:
        reported.append(result.item_id)

    results = asyncio.run(
        run_evaluation(dataset, variants, generate, on_result=on_result)
    )

    assert len(results) == 1
    assert reported == ["1"]


def test_runner_skips_already_persisted_pairs() -> None:
    dataset = [
        DatasetItem(id="1", input="First", expected_output="Answer"),
        DatasetItem(id="2", input="Second", expected_output="Answer"),
    ]
    variants = [Variant(name="test", model="test")]
    prompts = []

    async def generate(prompt: str, variant: Variant) -> str:
        prompts.append(prompt)
        return "Answer"

    results = asyncio.run(
        run_evaluation(
            dataset,
            variants,
            generate,
            skip_pairs={("1", "test")},
        )
    )

    assert [result.item_id for result in results] == ["2"]
    assert prompts == ["Second"]
