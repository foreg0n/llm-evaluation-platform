from __future__ import annotations

from typing import Protocol

from pydantic import SecretStr

from backend.credential_security import CredentialPayload
from evals.models import Variant
from evals.providers import LiteLLMProvider


class ProviderCredentialTesterProtocol(Protocol):
    async def test(self, model: str, payload: CredentialPayload) -> None: ...


class ProviderCredentialTester:
    """Perform a minimal completion only after an explicit user request."""

    def __init__(self, provider: LiteLLMProvider | None = None) -> None:
        self._provider = provider or LiteLLMProvider()

    async def test(self, model: str, payload: CredentialPayload) -> None:
        variant = Variant(
            name="credential-connection-test",
            model=model,
            temperature=0,
            max_tokens=1,
            timeout_seconds=15,
            max_retries=0,
            api_key=SecretStr(payload["api_key"]),
            api_base=payload["api_base"],
        )
        await self._provider.generate("Reply with OK.", variant)


def get_provider_credential_tester() -> ProviderCredentialTesterProtocol:
    return ProviderCredentialTester()
