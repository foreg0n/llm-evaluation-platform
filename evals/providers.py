from collections.abc import Callable

from evals.models import Variant

ProviderFunction = Callable[[str, Variant], str]


def fake_qwen(question: str, variant: Variant) -> str:
    del variant

    if "France" in question:
        return "The capital of France is Paris."
    if "5 + 7" in question:
        return "12"
    if "Docker" in question:
        return "Docker runs applications in containers."
    if "key-value" in question:
        return "dict"
    if "status" in question:
        return '{"status":"ok"}'
    return "I do not know."


def fake_llama(question: str, variant: Variant) -> str:
    del variant

    if "France" in question:
        return "Paris"
    if "5 + 7" in question:
        return "The answer is 12."
    if "Docker" in question:
        return "Docker is a tool for working with applications."
    if "key-value" in question:
        return "Dictionary"
    if "status" in question:
        return "status: ok"
    return "No answer available."


PROVIDERS: dict[str, ProviderFunction] = {
    "fake_qwen": fake_qwen,
    "fake_llama": fake_llama,
}


def generate(prompt: str, variant: Variant) -> str:
    try:
        provider_function = PROVIDERS[variant.model]
    except KeyError as exc:
        raise ValueError(f"Unknown fake model: {variant.model}") from exc

    return provider_function(prompt, variant)
