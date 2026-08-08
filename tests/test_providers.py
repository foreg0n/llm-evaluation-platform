from types import SimpleNamespace

import pytest

from evals.models import GenerationResponse, Variant
from evals.providers import (
    LLMProvider,
    LiteLLMProvider,
    ProviderExecutionError,
)


def make_response(content: str = "Paris") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=content))
        ],
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=2,
            total_tokens=12,
        ),
    )


def test_litellm_provider_maps_output_usage_cost_and_options() -> None:
    calls: list[dict[str, object]] = []

    def completion(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return make_response()

    provider = LiteLLMProvider(
        completion_function=completion,
        cost_function=lambda **kwargs: 0.0012,
    )
    assert isinstance(provider, LLMProvider)
    variant = Variant(
        name="real",
        model="groq/llama-3.3-70b-versatile",
        provider="litellm",
        system_prompt="Answer briefly.",
        timeout_seconds=5,
        max_tokens=100,
    )

    response = provider.generate("Capital of France?", variant)

    assert response.output == "Paris"
    assert response.input_tokens == 10
    assert response.output_tokens == 2
    assert response.total_tokens == 12
    assert response.estimated_cost == pytest.approx(0.0012)
    assert calls[0]["model"] == "groq/llama-3.3-70b-versatile"
    assert calls[0]["timeout"] == 5
    assert calls[0]["max_tokens"] == 100
    assert calls[0]["num_retries"] == 0
    assert calls[0]["messages"] == [
        {"role": "system", "content": "Answer briefly."},
        {"role": "user", "content": "Capital of France?"},
    ]


def test_litellm_provider_retries_timeout_without_network() -> None:
    attempts = 0
    delays: list[float] = []

    def completion(**kwargs: object) -> SimpleNamespace:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("temporary timeout")
        return make_response("Recovered")

    provider = LiteLLMProvider(
        completion_function=completion,
        cost_function=lambda **kwargs: 0.0,
        sleep_function=delays.append,
    )
    variant = Variant(
        name="real",
        model="groq/llama-3.3-70b-versatile",
        provider="litellm",
        max_retries=2,
    )

    response = provider.generate("Question", variant)

    assert response.output == "Recovered"
    assert response.retry_count == 2
    assert attempts == 3
    assert delays == [1, 2]


def test_litellm_provider_reports_exhausted_retries() -> None:
    attempts = 0

    def completion(**kwargs: object) -> SimpleNamespace:
        nonlocal attempts
        attempts += 1
        raise TimeoutError("provider timeout")

    provider = LiteLLMProvider(
        completion_function=completion,
        sleep_function=lambda seconds: None,
    )
    variant = Variant(
        name="real",
        model="groq/llama-3.3-70b-versatile",
        provider="litellm",
        max_retries=2,
    )

    with pytest.raises(ProviderExecutionError) as error:
        provider.generate("Question", variant)

    assert error.value.retry_count == 2
    assert attempts == 3
