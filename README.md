# LLM Evaluation Platform

A lightweight command-line evaluation framework for comparing language model
variants against the same JSONL dataset.

This first-stage implementation uses deterministic fake providers, making it
possible to validate the evaluation pipeline without API keys, network calls,
or usage costs.

## Features

- JSONL dataset loading and Pydantic validation
- Multiple model variants evaluated against the same inputs
- Exact match, normalized exact match, and keyword coverage metrics
- Per-request latency measurement
- Error isolation so one failed request does not stop the full run
- Aggregated comparison table rendered with Rich
- Reproducible JSON reports
- Pytest test suite

## Requirements

- Python 3.12 or newer

## Installation

Clone the repository and enter the project directory:

```bash
git clone <repository-url>
cd llm-evaluation-platform
```

Create and activate a virtual environment.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS or Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Install the project and development dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Running an Evaluation

```bash
python -m evals.run
```

The command prints a summary table containing quality, latency, and error
statistics for each variant. The complete report is written to:

```text
artifacts/results.json
```

## Running Tests

```bash
pytest
```

## Dataset Format

Each line in `evals/datasets/questions.jsonl` is an independent JSON object:

```json
{
  "id": "1",
  "input": "What is the capital of France?",
  "expected_output": "Paris",
  "keywords": ["Paris"]
}
```

Fields:

- `id`: unique test case identifier
- `input`: prompt sent to every selected variant
- `expected_output`: reference answer used by comparison metrics
- `keywords`: terms expected in a valid answer

## Metrics

| Metric | Description |
| --- | --- |
| Exact match | Compares lowercased, trimmed strings |
| Normalized exact match | Also removes punctuation and collapses whitespace |
| Keyword score | Measures the fraction of required keywords found |

For this MVP, overall quality is the arithmetic mean of the three metric
scores. Individual metric values remain available in the JSON report.

## Project Structure

```text
llm-evaluation-platform/
├── evals/
│   ├── datasets/
│   │   └── questions.jsonl
│   ├── __init__.py
│   ├── dataset.py
│   ├── metrics.py
│   ├── models.py
│   ├── providers.py
│   ├── run.py
│   └── runner.py
├── artifacts/
├── tests/
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

## Current Scope

This repository contains the CLI evaluation core. It intentionally does not
yet include real LLM APIs, a web API, persistent storage, background workers,
or a frontend.

Possible next steps include a common provider interface, LiteLLM integration,
async concurrency, retries, token and cost tracking, and additional metrics.
