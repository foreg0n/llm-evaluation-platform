from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.schemas import DatasetItemCreate

MAX_DATASET_FILE_BYTES = 5 * 1024 * 1024
MAX_DATASET_IMPORT_ITEMS = 1_000
SUPPORTED_DATASET_EXTENSIONS = frozenset({".json", ".jsonl", ".ndjson"})


class DatasetImportError(ValueError):
    """Raised when an uploaded dataset cannot be parsed or validated."""


@dataclass(frozen=True)
class ParsedDatasetImport:
    name: str | None
    description: str | None
    items: list[DatasetItemCreate]


def parse_dataset_file(filename: str, content: bytes) -> ParsedDatasetImport:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_DATASET_EXTENSIONS:
        raise DatasetImportError("Only .json, .jsonl, and .ndjson files are supported")
    if not content:
        raise DatasetImportError("The uploaded file is empty")
    if len(content) > MAX_DATASET_FILE_BYTES:
        raise DatasetImportError("The uploaded file exceeds the 5 MB limit")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DatasetImportError("The uploaded file must use UTF-8 encoding") from exc

    if extension in {".jsonl", ".ndjson"}:
        raw_items = _parse_json_lines(text)
        name = None
        description = None
    else:
        name, description, raw_items = _parse_json_document(text)

    if not raw_items:
        raise DatasetImportError("The dataset must contain at least one test case")
    if len(raw_items) > MAX_DATASET_IMPORT_ITEMS:
        raise DatasetImportError(
            f"A dataset import is limited to {MAX_DATASET_IMPORT_ITEMS} test cases"
        )

    items = [
        _validate_item(raw_item, position)
        for position, raw_item in enumerate(raw_items, start=1)
    ]
    external_ids = [item.external_id for item in items]
    duplicate_ids = sorted(
        external_id
        for external_id in set(external_ids)
        if external_ids.count(external_id) > 1
    )
    if duplicate_ids:
        preview = ", ".join(duplicate_ids[:5])
        raise DatasetImportError(f"Duplicate test case IDs: {preview}")

    return ParsedDatasetImport(
        name=_optional_string(name, "name"),
        description=_optional_string(description, "description"),
        items=items,
    )


def default_dataset_name(filename: str) -> str:
    return Path(filename).stem.strip() or "Imported dataset"


def _parse_json_lines(text: str) -> list[Any]:
    items: list[Any] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise DatasetImportError(
                f"Line {line_number} is not valid JSON: {exc.msg}"
            ) from exc
    return items


def _parse_json_document(text: str) -> tuple[Any, Any, list[Any]]:
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DatasetImportError(
            f"The file is not valid JSON at line {exc.lineno}: {exc.msg}"
        ) from exc

    if isinstance(document, list):
        return None, None, document
    if not isinstance(document, dict):
        raise DatasetImportError("A JSON dataset must be an array or an object")
    if "items" in document:
        raw_items = document["items"]
        if not isinstance(raw_items, list):
            raise DatasetImportError("The JSON 'items' field must be an array")
        return document.get("name"), document.get("description"), raw_items
    if "input" in document:
        return None, None, [document]
    raise DatasetImportError(
        "A JSON object must contain an 'items' array or represent one test case"
    )


def _validate_item(raw_item: Any, position: int) -> DatasetItemCreate:
    if not isinstance(raw_item, dict):
        raise DatasetImportError(f"Test case {position} must be a JSON object")
    normalized = dict(raw_item)
    if "external_id" not in normalized and "id" in normalized:
        normalized["external_id"] = normalized.pop("id")
    try:
        return DatasetItemCreate.model_validate(normalized)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        location = ".".join(str(part) for part in first_error["loc"])
        message = first_error["msg"]
        raise DatasetImportError(
            f"Test case {position}, field '{location}': {message}"
        ) from exc


def _optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DatasetImportError(f"Dataset {field} must be a string")
    return value
