import pytest

from evals.run import DEFAULT_GROQ_MODELS, build_variants, parse_args


def test_default_cli_builds_two_comparison_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    args = parse_args([])
    variants = build_variants(args)

    assert [variant.model for variant in variants] == list(
        DEFAULT_GROQ_MODELS
    )
    assert [variant.name for variant in variants] == [
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-20b",
    ]
    assert all(variant.provider == "litellm" for variant in variants)
    assert args.concurrency == 3


def test_cli_accepts_repeated_model_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    args = parse_args(
        [
            "--model",
            "qwen/qwen3.6-27b",
            "--model",
            "groq/openai/gpt-oss-20b",
            "--timeout",
            "15",
            "--max-retries",
            "3",
        ]
    )

    variants = build_variants(args)

    assert [variant.model for variant in variants] == [
        "groq/qwen/qwen3.6-27b",
        "groq/openai/gpt-oss-20b",
    ]
    assert all(variant.timeout_seconds == 15 for variant in variants)
    assert all(variant.max_retries == 3 for variant in variants)


def test_cli_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    args = parse_args([])

    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        build_variants(args)


def test_cli_rejects_invalid_concurrency() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--concurrency", "0"])
