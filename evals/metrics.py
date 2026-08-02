import re
import string

from evals.models import MetricScores


def exact_match(output: str, expected: str) -> float:
    return 1.0 if output.lower().strip() == expected.lower().strip() else 0.0


def normalize_text(value: str) -> str:
    lowered = value.lower()
    punctuation_table = str.maketrans("", "", string.punctuation + "«»—–…")
    without_punctuation = lowered.translate(punctuation_table)
    collapsed_spaces = re.sub(r"\s+", " ", without_punctuation).strip()

    return collapsed_spaces


def normalized_exact_match(output: str, expected: str) -> float:
    return 1.0 if normalize_text(output) == normalize_text(expected) else 0.0


def keyword_score(output: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0

    normalized_output = normalize_text(output)
    found = 0

    for keyword in keywords:
        if normalize_text(keyword) in normalized_output:
            found += 1

    return found / len(keywords)


def calculate_metrics(
    output: str,
    expected: str,
    keywords: list[str],
) -> MetricScores:
    return MetricScores(
        exact_match=exact_match(output, expected),
        normalized_exact_match=normalized_exact_match(output, expected),
        keyword_score=keyword_score(output, keywords),
    )

