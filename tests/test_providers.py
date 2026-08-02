import pytest

from evals.models import Variant
from evals.providers import generate


@pytest.mark.parametrize("model", ["fake_qwen", "fake_llama"])
def test_registered_provider_returns_text(model: str) -> None:
    variant = Variant(name=model, model=model)
    assert generate("What is the capital of France?", variant)


def test_unknown_provider_is_rejected() -> None:
    variant = Variant(name="unknown", model="unknown")

    with pytest.raises(ValueError, match="Unknown"):
        generate("Question", variant)
