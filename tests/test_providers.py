import asyncio
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from evals.models import Variant
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


def test_litellm_provider_forwards_credentials_without_serializing_them() -> None:
    calls: list[dict[str, object]] = []

    async def completion(**kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return make_response()

    provider = LiteLLMProvider(
        completion_function=completion,
        cost_function=lambda **kwargs: 0,
    )
    variant = Variant(
        name="Claude",
        model="anthropic/claude-test",
        api_key=SecretStr("private-provider-key"),
        api_base="https://provider.example/v1",
        max_retries=0,
    )

    response = asyncio.run(provider.generate("Hello", variant))

    assert response.output == "Paris"
    assert calls[0]["api_key"] == "private-provider-key"
    assert calls[0]["api_base"] == "https://provider.example/v1"
    assert "api_key" not in variant.model_dump()
    assert "private-provider-key" not in repr(variant)


def test_provider_error_redacts_the_active_api_key() -> None:
    async def completion(**_kwargs: object) -> SimpleNamespace:
        raise RuntimeError("Rejected private-provider-key")

    provider = LiteLLMProvider(
        completion_function=completion,
        cost_function=lambda **kwargs: 0,
    )
    variant = Variant(
        name="Broken",
        model="openai/test",
        api_key=SecretStr("private-provider-key"),
        max_retries=0,
    )

    with pytest.raises(ProviderExecutionError) as captured:
        asyncio.run(provider.generate("Hello", variant))

    assert "private-provider-key" not in str(captured.value)
    assert "[Filtered]" in str(captured.value)


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
