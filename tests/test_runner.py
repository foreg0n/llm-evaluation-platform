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

    results = run_evaluation(dataset, variants, lambda prompt, variant: "12")

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

    def broken_provider(prompt: str, variant: Variant) -> str:
        raise TimeoutError("provider timeout")

    results = run_evaluation(dataset, variants, broken_provider)

    assert len(results) == 1
    assert results[0].output is None
    assert "TimeoutError" in (results[0].error or "")


def test_runner_continues_after_one_provider_error() -> None:
    dataset = [
        DatasetItem(id="1", input="Fail", expected_output="Answer"),
        DatasetItem(id="2", input="Succeed", expected_output="Answer"),
    ]
    variants = [Variant(name="real", model="real")]

    def sometimes_fails(
        prompt: str,
        variant: Variant,
    ) -> GenerationResponse:
        if prompt == "Fail":
            raise ProviderExecutionError("TimeoutError: timeout", retry_count=2)
        return GenerationResponse(output="Answer")

    results = run_evaluation(dataset, variants, sometimes_fails)

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

    results = run_evaluation(
        dataset,
        variants,
        lambda prompt, variant: GenerationResponse(
            output="Answer",
            input_tokens=8,
            output_tokens=2,
            total_tokens=10,
            estimated_cost=0.001,
            retry_count=1,
        ),
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
    results = run_evaluation(
        dataset,
        variants,
        lambda prompt, variant: "Answer",
    )

    summary = summarize_results(results, variants)

    assert summary[0].average_quality == 1.0
    assert summary[0].error_count == 0
