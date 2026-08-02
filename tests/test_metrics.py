import pytest

from evals.metrics import (
    exact_match,
    keyword_score,
    normalize_text,
    normalized_exact_match,
)


def test_exact_match_equal() -> None:
    assert exact_match("Paris", "Paris") == 1.0


def test_exact_match_different() -> None:
    assert exact_match("The capital is Paris", "Paris") == 0.0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  PARIS. ", "paris"),
        ("one   two", "one two"),
        ("Docker — containers!", "docker containers"),
    ],
)
def test_normalize_text(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_normalized_exact_match() -> None:
    assert normalized_exact_match(" PARIS. ", "paris") == 1.0


def test_keyword_score_all_found() -> None:
    output = "The item can be returned within 14 days with a receipt."
    assert keyword_score(output, ["14 days", "receipt"]) == 1.0


def test_keyword_score_partial() -> None:
    output = "The item can be returned within 14 days."
    assert keyword_score(output, ["14 days", "receipt"]) == 0.5


def test_keyword_score_empty_keywords() -> None:
    assert keyword_score("Any answer", []) == 1.0
