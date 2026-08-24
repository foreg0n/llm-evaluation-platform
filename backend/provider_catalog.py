from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    slug: str
    label: str
    model_prefix: str
    api_key_placeholder: str
    supports_custom_base_url: bool = False


PROVIDER_CATALOG = (
    ProviderDefinition("groq", "Groq", "groq/", "gsk_••••••••"),
    ProviderDefinition("openai", "OpenAI", "openai/", "sk-••••••••"),
    ProviderDefinition(
        "anthropic", "Anthropic · Claude", "anthropic/", "sk-ant-••••••••"
    ),
    ProviderDefinition("gemini", "Google · Gemini", "gemini/", "AIza••••••••"),
    ProviderDefinition(
        "openrouter", "OpenRouter", "openrouter/", "sk-or-••••••••"
    ),
    ProviderDefinition("mistral", "Mistral AI", "mistral/", "••••••••"),
    ProviderDefinition("deepseek", "DeepSeek", "deepseek/", "sk-••••••••"),
    ProviderDefinition("xai", "xAI · Grok", "xai/", "xai-••••••••"),
    ProviderDefinition("cohere", "Cohere", "cohere_chat/", "••••••••"),
    ProviderDefinition(
        "together_ai", "Together AI", "together_ai/", "••••••••"
    ),
    ProviderDefinition(
        "fireworks_ai", "Fireworks AI", "fireworks_ai/", "fw_••••••••"
    ),
    ProviderDefinition(
        "perplexity", "Perplexity", "perplexity/", "pplx-••••••••"
    ),
    ProviderDefinition("cerebras", "Cerebras", "cerebras/", "csk-••••••••"),
    ProviderDefinition("sambanova", "SambaNova", "sambanova/", "••••••••"),
    ProviderDefinition(
        "custom",
        "Custom OpenAI-compatible",
        "openai/",
        "API key",
        supports_custom_base_url=True,
    ),
)

PROVIDERS_BY_SLUG = {provider.slug: provider for provider in PROVIDER_CATALOG}


def get_provider_definition(slug: str) -> ProviderDefinition | None:
    return PROVIDERS_BY_SLUG.get(slug)
