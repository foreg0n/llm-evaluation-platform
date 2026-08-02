from pathlib import Path

import pytest

from evals.dataset import load_dataset


def test_load_dataset(tmp_path: Path) -> None:
    dataset_path = tmp_path / "questions.jsonl"
    dataset_path.write_text(
        '{"id":"1","input":"Question","expected_output":"Answer"}\n',
        encoding="utf-8",
    )

    items = load_dataset(dataset_path)

    assert len(items) == 1
    assert items[0].id == "1"


def test_load_dataset_reports_invalid_line(tmp_path: Path) -> None:
    dataset_path = tmp_path / "broken.jsonl"
    dataset_path.write_text('{"id":\n', encoding="utf-8")

    with pytest.raises(ValueError, match="line 1"):
        load_dataset(dataset_path)
