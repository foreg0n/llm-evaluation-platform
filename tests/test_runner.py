from evals.models import DatasetItem, Variant
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
