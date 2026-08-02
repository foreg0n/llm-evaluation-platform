import json
from pathlib import Path

from pydantic import ValidationError

from evals.models import DatasetItem


def load_dataset(path: Path) -> list[DatasetItem]:
    if not path.is_file():
        raise FileNotFoundError(f"Dataset not found: {path}")

    items: list[DatasetItem] = []

    with path.open("r", encoding="utf-8") as dataset_file:
        for line_number, raw_line in enumerate(dataset_file, start=1):
            if not raw_line.strip():
                continue

            try:
                payload = json.loads(raw_line)
                item = DatasetItem.model_validate(payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                raise ValueError(
                    f"Invalid line {line_number} in {path}: {exc}"
                ) from exc

            items.append(item)

    if not items:
        raise ValueError(f"Dataset is empty: {path}")

    return items
