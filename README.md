# LLM Evaluation Platform

A lightweight command-line framework for comparing real language models on
GroqCloud against a reusable JSONL dataset.

## Features

- Real GroqCloud API calls through LiteLLM
- Qwen 3.6 27B and GPT-OSS 20B compared in every default run
- Asynchronous requests with configurable concurrency
- A shared provider protocol for clean model integration
- JSONL dataset loading and Pydantic validation
- Exact match, normalized exact match, and keyword coverage metrics
- Per-request latency, token usage, estimated cost, and retry tracking
- Configurable timeouts and bounded exponential-backoff retries
- Error isolation: one failed request does not stop the evaluation run
- Rich terminal summary and a reproducible JSON report
- Network-free tests using mocked Groq responses

## Requirements

- Python 3.12 or newer
- A GroqCloud account and API key

## Installation

Clone the repository and enter its directory:

```bash
git clone https://github.com/foreg0n/llm-evaluation-platform.git
cd llm-evaluation-platform
```

Create and activate a virtual environment.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
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

## Groq API Key

1. Sign in to the [GroqCloud Console](https://console.groq.com/).
2. Create a key on the [Groq API Keys page](https://console.groq.com/keys).
3. Copy the environment template:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS or Linux:

```bash
cp .env.example .env
```

4. Add your key to `.env`:

```dotenv
GROQ_API_KEY=your-secret-groq-key
```

The `.env` file is ignored by Git. Never commit, publish, or share your API
key. Revoke it immediately in the GroqCloud Console if it is exposed.

## Running an Evaluation

The default run compares these two models:

- `groq/qwen/qwen3.6-27b`
- `groq/openai/gpt-oss-20b`

The included dataset contains five items, so the default comparison produces
ten real API requests per run.

```bash
python -m evals.run --concurrency 3
```

`--concurrency` controls the maximum number of in-flight model requests. Its
default value is `3`; lower it if Groq returns rate-limit errors.

Override request settings when necessary:

```bash
python -m evals.run \
  --temperature 0 \
  --max-tokens 500 \
  --system-prompt "Answer accurately and concisely." \
  --timeout 30 \
  --max-retries 2 \
  --concurrency 3
```

To compare a custom model set, repeat `--model`:

```bash
python -m evals.run \
  --model qwen/qwen3.6-27b \
  --model openai/gpt-oss-20b
```

The LiteLLM `groq/` prefix is optional and is added automatically. Run
`python -m evals.run --help` for all options.

The terminal displays an aggregate summary. The complete report is written to
`artifacts/results.json` and includes the answer, quality metrics, latency,
token usage, estimated cost, retry count, and provider errors for every item.

## Running Tests

```bash
pytest
```

Tests inject mocked completion functions into `LiteLLMProvider`. They do not
read your API key and never send requests to GroqCloud.

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

- `id`: unique test case identifier
- `input`: prompt sent to the model
- `expected_output`: reference answer used by comparison metrics
- `keywords`: terms expected in a valid answer

## Metrics

| Metric | Description |
| --- | --- |
| Exact match | Compares lowercased, trimmed strings |
| Normalized exact match | Also removes punctuation and collapses whitespace |
| Keyword score | Measures the fraction of required keywords found |

Overall quality is the arithmetic mean of the three scores. Individual metric
values remain available in the JSON report.

## Provider Architecture

The runner depends on a small shared interface:

```python
class AsyncLLMProvider(Protocol):
    async def generate(
        self,
        prompt: str,
        variant: Variant,
    ) -> GenerationResponse:
        ...
```

`LiteLLMProvider` implements this interface with `litellm.acompletion` and maps
a Groq completion into the project's `GenerationResponse`, including token and
cost data. The runner creates one task per dataset-item/model pair and uses an
`asyncio.Semaphore` to enforce the requested concurrency limit. Temporary
connection, timeout, rate-limit, server, and invalid-response failures use
bounded exponential backoff. Authentication and validation errors fail
immediately, while the runner records the error and continues with later items.

## Project Structure

```text
llm-evaluation-platform/
├── evals/
│   ├── datasets/
│   │   └── questions.jsonl
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

This repository contains the synchronous CLI evaluation core for comparing
models on GroqCloud. It does not yet include a web API, persistent storage,
background workers, distributed rate limiting, or a frontend.

Possible next steps include async concurrency, FastAPI, PostgreSQL, experiment
history, background workers, and additional evaluation metrics.
