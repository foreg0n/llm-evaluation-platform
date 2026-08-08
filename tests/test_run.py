import pytest

from evals.run import DEFAULT_GROQ_MODEL, build_variants, parse_args


def test_default_cli_builds_real_groq_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    variants = build_variants(parse_args([]))

    assert len(variants) == 1
    assert variants[0].model == DEFAULT_GROQ_MODEL
    assert variants[0].provider == "litellm"


def test_cli_builds_litellm_variant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    args = parse_args(
        [
            "--model",
            "llama-3.3-70b-versatile",
            "--timeout",
            "15",
            "--max-retries",
            "3",
        ]
    )

    variant = build_variants(args)[0]

    assert variant.provider == "litellm"
    assert variant.model == "groq/llama-3.3-70b-versatile"
    assert variant.timeout_seconds == 15
    assert variant.max_retries == 3


def test_cli_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    args = parse_args([])

    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        build_variants(args)


def test_cli_uses_model_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "groq/llama-3.3-70b-versatile")

    variant = build_variants(parse_args([]))[0]

    assert variant.model == "groq/llama-3.3-70b-versatile"
