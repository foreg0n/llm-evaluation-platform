import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, runtime_checkable

from evals.models import GenerationResponse, Variant

AsyncCompletionFunction = Callable[..., Awaitable[Any]]
CostFunction = Callable[..., float]
AsyncSleepFunction = Callable[[float], Awaitable[None]]


class ProviderExecutionError(RuntimeError):
    """A provider failure that retains the number of retries performed."""

    def __init__(self, message: str, retry_count: int) -> None:
        super().__init__(message)
        self.retry_count = retry_count


class InvalidProviderResponseError(RuntimeError):
    """Raised when a provider returns no usable assistant text."""


@runtime_checkable
class AsyncLLMProvider(Protocol):
    async def generate(
        self,
        prompt: str,
        variant: Variant,
    ) -> GenerationResponse:
        """Generate one response for a rendered prompt."""
        ...


async def _default_acompletion(**kwargs: Any) -> Any:
    from litellm import acompletion

    return await acompletion(**kwargs)


def _default_completion_cost(**kwargs: Any) -> float:
    from litellm import completion_cost

    return float(completion_cost(**kwargs))


class LiteLLMProvider:
    """Async provider backed by LiteLLM's unified completion API."""

    def __init__(
        self,
        completion_function: AsyncCompletionFunction = _default_acompletion,
        cost_function: CostFunction = _default_completion_cost,
        sleep_function: AsyncSleepFunction = asyncio.sleep,
    ) -> None:
        self._completion = completion_function
        self._completion_cost = cost_function
        self._sleep = sleep_function

    async def generate(
        self,
        prompt: str,
        variant: Variant,
    ) -> GenerationResponse:
        messages = self._build_messages(prompt, variant.system_prompt)
        retry_count = 0

        while True:
            try:
                response = await self._completion(
                    model=variant.model,
                    messages=messages,
                    temperature=variant.temperature,
                    max_tokens=variant.max_tokens,
                    timeout=variant.timeout_seconds,
                    num_retries=0,
                )
                return self._to_generation_response(
                    response=response,
                    model=variant.model,
                    retry_count=retry_count,
                )
            except Exception as exc:
                if (
                    retry_count >= variant.max_retries
                    or not self._is_retryable(exc)
                ):
                    raise ProviderExecutionError(
                        f"{type(exc).__name__}: {exc}",
                        retry_count=retry_count,
                    ) from exc

                delay_seconds = min(2**retry_count, 8)
                retry_count += 1
                await self._sleep(delay_seconds)

    @staticmethod
    def _build_messages(
        prompt: str,
        system_prompt: str | None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _to_generation_response(
        self,
        response: Any,
        model: str,
        retry_count: int,
    ) -> GenerationResponse:
        choices = self._read_field(response, "choices", [])
        if not choices:
            raise InvalidProviderResponseError("Response contains no choices")

        message = self._read_field(choices[0], "message")
        output = self._read_field(message, "content") if message else None
        if not isinstance(output, str) or not output.strip():
            raise InvalidProviderResponseError(
                "Response contains no assistant text"
            )

        usage = self._read_field(response, "usage")
        input_tokens = self._optional_int(
            self._read_field(usage, "prompt_tokens") if usage else None
        )
        output_tokens = self._optional_int(
            self._read_field(usage, "completion_tokens") if usage else None
        )
        total_tokens = self._optional_int(
            self._read_field(usage, "total_tokens") if usage else None
        )

        try:
            estimated_cost = self._completion_cost(
                completion_response=response,
                model=model,
            )
        except Exception:
            estimated_cost = None

        return GenerationResponse(
            output=output,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost,
            retry_count=retry_count,
        )

    @staticmethod
    def _read_field(
        value: Any,
        field_name: str,
        default: Any = None,
    ) -> Any:
        if isinstance(value, Mapping):
            return value.get(field_name, default)
        return getattr(value, field_name, default)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return int(value) if value is not None else None

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        retryable_names = {
            "APIConnectionError",
            "APITimeoutError",
            "InternalServerError",
            "RateLimitError",
            "ServiceUnavailableError",
            "Timeout",
        }
        return isinstance(
            exc,
            (TimeoutError, ConnectionError, InvalidProviderResponseError),
        ) or type(exc).__name__ in retryable_names


DEFAULT_PROVIDER: AsyncLLMProvider = LiteLLMProvider()


async def generate(
    prompt: str,
    variant: Variant,
    provider: AsyncLLMProvider | None = None,
) -> GenerationResponse:
    active_provider = provider or DEFAULT_PROVIDER
    return await active_provider.generate(prompt, variant)
