from __future__ import annotations

import asyncio
from typing import Protocol

from pydantic import SecretStr

from backend.credential_security import CredentialPayload
from backend.network_security import validate_provider_endpoint
from evals.models import Variant
from evals.providers import LiteLLMProvider


class ProviderCredentialTesterProtocol(Protocol):
    async def test(self, model: str, payload: CredentialPayload) -> None: ...


class ProviderCredentialTester:
    """Perform a minimal completion only after an explicit user request."""

    def __init__(self, provider: LiteLLMProvider | None = None) -> None:
        self._provider = provider or LiteLLMProvider()

    async def test(self, model: str, payload: CredentialPayload) -> None:
        if payload["api_base"] is not None:
            await asyncio.to_thread(
                validate_provider_endpoint,
                payload["api_base"],
            )
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
