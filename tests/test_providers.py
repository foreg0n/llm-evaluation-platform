import asyncio
from types import SimpleNamespace

import pytest

from evals.models import GenerationResponse, Variant
from evals.providers import (
    AsyncLLMProvider,
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

    async def completion(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return make_response()

    provider = LiteLLMProvider(
        completion_function=completion,
        cost_function=lambda **kwargs: 0.0012,
    )
    assert isinstance(provider, AsyncLLMProvider)
    variant = Variant(
        name="real",
        model="groq/qwen/qwen3.6-27b",
        provider="litellm",
        system_prompt="Answer briefly.",
        timeout_seconds=5,
        max_tokens=100,
    )

    response = asyncio.run(provider.generate("Capital of France?", variant))

    assert response.output == "Paris"
    assert response.input_tokens == 10
    assert response.output_tokens == 2
    assert response.total_tokens == 12
    assert response.estimated_cost == pytest.approx(0.0012)
    assert calls[0]["model"] == "groq/qwen/qwen3.6-27b"
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

    async def completion(**kwargs: object) -> SimpleNamespace:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("temporary timeout")
        return make_response("Recovered")

    async def sleep(seconds: float) -> None:
        delays.append(seconds)

    provider = LiteLLMProvider(
        completion_function=completion,
        cost_function=lambda **kwargs: 0.0,
        sleep_function=sleep,
    )
    variant = Variant(
        name="real",
        model="groq/openai/gpt-oss-20b",
        provider="litellm",
        max_retries=2,
    )

    response = asyncio.run(provider.generate("Question", variant))

    assert response.output == "Recovered"
    assert response.retry_count == 2
    assert attempts == 3
    assert delays == [1, 2]


def test_litellm_provider_reports_exhausted_retries() -> None:
    attempts = 0

    async def completion(**kwargs: object) -> SimpleNamespace:
        nonlocal attempts
        attempts += 1
        raise TimeoutError("provider timeout")

    async def no_sleep(seconds: float) -> None:
        return None

    provider = LiteLLMProvider(
        completion_function=completion,
        sleep_function=no_sleep,
    )
    variant = Variant(
        name="real",
        model="groq/openai/gpt-oss-20b",
        provider="litellm",
        max_retries=2,
    )

    with pytest.raises(ProviderExecutionError) as error:
        asyncio.run(provider.generate("Question", variant))

    assert error.value.retry_count == 2
    assert attempts == 3
