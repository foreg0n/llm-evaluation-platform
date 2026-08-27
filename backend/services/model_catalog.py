from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.request
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import lru_cache
from typing import Callable, Literal, Protocol

from backend.config import get_settings
from backend.credential_security import CredentialPayload
from backend.provider_catalog import get_provider_definition

logger = logging.getLogger(__name__)

CatalogSource = Literal["provider", "litellm", "manual"]
ModelLoader = Callable[[str, str | None, str | None], list[str]]

_OPENAI_COMPATIBLE_MODEL_URLS = {
    "groq": "https://api.groq.com/openai/v1/models",
    "openai": "https://api.openai.com/v1/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
    "mistral": "https://api.mistral.ai/v1/models",
    "deepseek": "https://api.deepseek.com/models",
    "xai": "https://api.x.ai/v1/models",
    "together_ai": "https://api.together.xyz/v1/models",
    "fireworks_ai": "https://api.fireworks.ai/inference/v1/models",
    "cerebras": "https://api.cerebras.ai/v1/models",
    "sambanova": "https://api.sambanova.ai/v1/models",
}


@dataclass(frozen=True, slots=True)
class ModelCatalogResult:
    models: tuple[str, ...]
    source: CatalogSource
    cached: bool
    refreshed_at: datetime
    warning: str | None = None


@dataclass(frozen=True, slots=True)
class _CachedCatalog:
    result: ModelCatalogResult
    expires_at: float


class ProviderModelCatalogProtocol(Protocol):
    async def discover(
        self,
        provider: str,
        payload: CredentialPayload,
        *,
        cache_key: str,
        force_refresh: bool = False,
    ) -> ModelCatalogResult: ...


def _litellm_provider(provider: str) -> str:
    if provider == "custom":
        return "openai"
    if provider == "cohere":
        return "cohere_chat"
    return provider


def _live_models(
    provider: str,
    api_key: str | None,
    api_base: str | None,
    *,
    timeout_seconds: float = 10,
) -> list[str]:
    if not api_key:
        return []

    url, headers = _model_request(provider, api_key, api_base)
    if url is None:
        return []

    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        document = json.load(response)
    return _model_ids(document)


def _model_request(
    provider: str,
    api_key: str,
    api_base: str | None,
) -> tuple[str | None, dict[str, str]]:
    if provider == "custom":
        if not api_base:
            return None, {}
        normalized_base = api_base.rstrip("/")
        url = (
            f"{normalized_base}/models"
            if normalized_base.endswith("/v1")
            else f"{normalized_base}/v1/models"
        )
        return url, {"Authorization": f"Bearer {api_key}"}

    if provider == "gemini":
        return (
            "https://generativelanguage.googleapis.com/v1beta/models",
            {"x-goog-api-key": api_key},
        )
    if provider == "anthropic":
        return (
            "https://api.anthropic.com/v1/models",
            {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )
    if provider == "cohere":
        return (
            "https://api.cohere.com/v1/models",
            {"Authorization": f"Bearer {api_key}"},
        )

    url = _OPENAI_COMPATIBLE_MODEL_URLS.get(provider)
    if url is None:
        return None, {}
    return url, {"Authorization": f"Bearer {api_key}"}


def _model_ids(document: object) -> list[str]:
    if not isinstance(document, dict):
        return []
    records = document.get("data")
    if not isinstance(records, list):
        records = document.get("models")
    if not isinstance(records, list):
        return []

    models: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        supported_methods = record.get("supportedGenerationMethods")
        if (
            isinstance(supported_methods, list)
            and "generateContent" not in supported_methods
        ):
            continue
        model_id = record.get("id") or record.get("name")
        if isinstance(model_id, str):
            models.append(model_id)
    return models


def _fallback_models(
    provider: str,
    _api_key: str | None,
    _api_base: str | None,
) -> list[str]:
    from litellm import get_valid_models

    if provider == "custom":
        return []
    return list(
        get_valid_models(
            check_provider_endpoint=False,
            custom_llm_provider=_litellm_provider(provider),
        )
    )


def _normalize_model(provider: str, value: object) -> str | None:
    if not isinstance(value, str):
        return None
    model = value.strip()
    if model.startswith("models/"):
        model = model.removeprefix("models/")
    if not model or len(model) > 300 or any(ord(character) < 32 for character in model):
        return None

    definition = get_provider_definition(provider)
    prefix = definition.model_prefix if definition is not None else f"{provider}/"
    if model.startswith(prefix):
        return model
    return f"{prefix}{model}"


class ProviderModelCatalog:
    """Discover provider models without persisting or returning API keys."""

    def __init__(
        self,
        *,
        live_loader: ModelLoader | None = None,
        fallback_loader: ModelLoader = _fallback_models,
        timeout_seconds: float = 10,
        cache_ttl_seconds: int = 300,
        maximum_models: int = 500,
        maximum_cache_entries: int = 256,
    ) -> None:
        if live_loader is None:
            self._live_loader = lambda provider, api_key, api_base: _live_models(
                provider,
                api_key,
                api_base,
                timeout_seconds=timeout_seconds,
            )
        else:
            self._live_loader = live_loader
        self._fallback_loader = fallback_loader
        self._timeout_seconds = timeout_seconds
        self._cache_ttl_seconds = cache_ttl_seconds
        self._maximum_models = maximum_models
        self._maximum_cache_entries = maximum_cache_entries
        self._cache: dict[str, _CachedCatalog] = {}

    async def discover(
        self,
        provider: str,
        payload: CredentialPayload,
        *,
        cache_key: str,
        force_refresh: bool = False,
    ) -> ModelCatalogResult:
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if not force_refresh and cached is not None and cached.expires_at > now:
            return replace(cached.result, cached=True)

        live_models = await self._run_loader(
            self._live_loader,
            provider,
            payload,
            event="provider_model_discovery_failed",
        )
        if live_models:
            result = self._result(provider, live_models, source="provider")
        else:
            fallback_models = await self._run_loader(
                self._fallback_loader,
                provider,
                {"api_key": "", "api_base": None},
                event="provider_model_fallback_failed",
            )
            source: CatalogSource = "litellm" if fallback_models else "manual"
            warning = (
                "Live discovery is unavailable; showing LiteLLM's built-in catalog."
                if fallback_models
                else "This provider did not return a model catalog; enter a model ID manually."
            )
            result = self._result(
                provider,
                fallback_models,
                source=source,
                warning=warning,
            )

        self._store(cache_key, result, now)
        return result

    async def _run_loader(
        self,
        loader: ModelLoader,
        provider: str,
        payload: CredentialPayload,
        *,
        event: str,
    ) -> list[str]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    loader,
                    provider,
                    payload["api_key"] or None,
                    payload["api_base"],
                ),
                timeout=self._timeout_seconds,
            )
        except Exception as exc:
            logger.warning(
                event,
                extra={
                    "provider": provider,
                    "error_type": type(exc).__name__,
                },
            )
            return []

    def _result(
        self,
        provider: str,
        models: list[str],
        *,
        source: CatalogSource,
        warning: str | None = None,
    ) -> ModelCatalogResult:
        normalized = {
            model
            for value in models
            if (model := _normalize_model(provider, value)) is not None
        }
        return ModelCatalogResult(
            models=tuple(sorted(normalized, key=str.casefold)[: self._maximum_models]),
            source=source,
            cached=False,
            refreshed_at=datetime.now(UTC),
            warning=warning,
        )

    def _store(
        self,
        cache_key: str,
        result: ModelCatalogResult,
        now: float,
    ) -> None:
        if self._cache_ttl_seconds <= 0:
            return
        expired = [
            key for key, value in self._cache.items() if value.expires_at <= now
        ]
        for key in expired:
            self._cache.pop(key, None)
        while len(self._cache) >= self._maximum_cache_entries:
            oldest_key = min(
                self._cache,
                key=lambda key: self._cache[key].expires_at,
            )
            self._cache.pop(oldest_key, None)
        self._cache[cache_key] = _CachedCatalog(
            result=result,
            expires_at=now + self._cache_ttl_seconds,
        )


@lru_cache
def get_provider_model_catalog() -> ProviderModelCatalogProtocol:
    settings = get_settings()
    return ProviderModelCatalog(
        timeout_seconds=settings.model_catalog_timeout_seconds,
        cache_ttl_seconds=settings.model_catalog_cache_ttl_seconds,
    )
