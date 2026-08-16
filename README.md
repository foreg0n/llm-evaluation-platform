# LLM Evaluation Platform

A full-stack evaluation platform for comparing real language models on
GroqCloud. It combines an asynchronous CLI, a FastAPI and PostgreSQL backend,
and a dark analytics frontend for everyday experiment management.

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
- FastAPI application with a database-aware health endpoint
- Async SQLAlchemy models and an Alembic migration for experiment history
- Versioned CRUD API for projects, datasets, dataset items, and model variants
- API-managed evaluation runs persisted in PostgreSQL
- Fast `202 Accepted` scheduling, progress polling, and run cancellation
- Argon2 password hashing and expiring JWT access tokens
- Per-user project ownership and data isolation across every protected endpoint
- Responsive React frontend with login, registration, and session handling
- Live overview dashboard backed by the projects and evaluation-runs APIs
- In-app project creation and browser-safe CORS configuration
- Project workspaces with real dataset and test-case CRUD operations
- Editable prompts, reference answers, and comma-separated evaluation keywords
- Atomic JSON, JSONL, and NDJSON dataset import with file-wide validation
- In-app model-variant creation, editing, and deletion
- Frontend evaluation launch with dataset, model, and concurrency selection
- Live run progress, cooperative cancellation, and partial-result polling
- Model leaderboard with quality, latency, token, cost, retry, and error data

## Requirements

- Python 3.12 or newer
- Node.js 22.13 or newer and npm
- A GroqCloud account and API key for real evaluations
- PostgreSQL for the backend API

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

## Starting the Backend

Create a PostgreSQL database, then set its async SQLAlchemy URL in `.env`:

```dotenv
DATABASE_URL=postgresql+asyncpg://postgres:change-me@localhost:5432/llm_evaluation
DATABASE_ECHO=false
AUTH_SECRET_KEY=replace-with-a-random-secret
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

Generate a strong signing secret instead of typing one manually:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the printed value into `AUTH_SECRET_KEY`. JWT payloads are signed, not
encrypted, so never put passwords, API keys, or other secrets inside them. Use
HTTPS outside local development.

Create or update the database schema:

```bash
python -m alembic upgrade head
```

Migration `20260815_0003` preserves projects created before authentication by
assigning them to an inactive `legacy-import@local.invalid` account. After you
register, a database administrator may explicitly reassign those projects to
your new user ID; they are never exposed automatically.

Start the API from the repository root:

```bash
python -m uvicorn backend.main:app --reload
```

The API is then available at `http://127.0.0.1:8000`, with interactive docs at
`http://127.0.0.1:8000/docs`.

## Starting the Frontend

Keep the backend running, then open a second terminal:

Windows PowerShell:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

macOS or Linux:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open the local URL printed by the development server, normally
`http://localhost:3000`. The frontend uses `NEXT_PUBLIC_API_URL` from
`frontend/.env.local`; it defaults to `http://127.0.0.1:8000`.

The access token is kept in `sessionStorage`, so closing the tab ends the local
browser session. This limits persistence but does not replace production-grade
XSS protections. A future production deployment should use HTTPS and consider
secure, HttpOnly cookies.

If the frontend runs on a different origin, add it to the comma-separated
`CORS_ORIGINS` value in the root `.env` file and restart FastAPI.

## Authentication

Register once, then exchange your credentials for a short-lived bearer token:

```powershell
$user = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/auth/register `
  -ContentType "application/json" `
  -Body '{"email":"you@example.com","password":"choose-a-long-password"}'

$login = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/auth/login `
  -ContentType "application/json" `
  -Body '{"email":"you@example.com","password":"choose-a-long-password"}'

$headers = @{ Authorization = "Bearer $($login.access_token)" }
```

The available auth endpoints are:

- `POST /api/v1/auth/register` for JSON registration
- `POST /api/v1/auth/login` for JSON login
- `POST /api/v1/auth/token` for the OAuth2 password form used by Swagger UI
- `GET /api/v1/auth/me` for the current account

The health endpoint and auth endpoints are public. Every project, dataset,
item, variant, run, and result endpoint requires `Authorization: Bearer ...`.
Users see only their own projects and all nested resources inherit that
ownership. Tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES`; sign in again to
obtain a new one.

## CRUD API

All data-management endpoints use the `/api/v1` prefix. Collection endpoints
support `offset` and `limit` query parameters; `limit` is capped at 100.

| Resource | Create and list | Read, update, and delete |
| --- | --- | --- |
| Projects | `POST/GET /api/v1/projects` | `/api/v1/projects/{project_id}` |
| Datasets | `POST/GET /api/v1/projects/{project_id}/datasets` | `/api/v1/datasets/{dataset_id}` |
| Dataset items | `POST/GET /api/v1/datasets/{dataset_id}/items` | `/api/v1/dataset-items/{item_id}` |
| Variants | `POST/GET /api/v1/projects/{project_id}/variants` | `/api/v1/variants/{variant_id}` |

### Importing a Dataset File

From a project workspace, select **Import file** and upload one of:

- `.jsonl` or `.ndjson`: one test-case object per non-empty line;
- `.json`: an array of test cases, a single test case, or an object containing
  `name`, `description`, and an `items` array.

Each test case uses the same shape as the CLI dataset:

```json
{"id":"capital-france","input":"What is the capital of France?","expected_output":"Paris","keywords":["Paris"]}
```

`external_id` is also accepted instead of `id`. Files must be UTF-8, no larger
than 5 MB, contain 1–1,000 test cases, and use unique IDs. The API validates the
whole file before committing a single transaction, so an invalid line never
leaves a partially imported dataset. A downloadable JSON template is available
in the import dialog.

The protected multipart endpoint is:

```text
POST /api/v1/projects/{project_id}/datasets/import
```

## Running an Evaluation from the Frontend

The complete experiment workflow is available without writing API requests:

1. Open a project and import or create a dataset with test cases.
2. Open **Models** and add the Groq model variants you want to compare.
   Evalflow includes suggestions for Qwen 3.6 27B and GPT OSS 20B, while the
   model ID field also accepts other LiteLLM-compatible Groq model IDs.
3. Open **Evaluation runs**, choose a dataset, select one or more models, set
   the number of parallel workers, and select **Start evaluation**.
4. Keep the run open to see task progress and partial results refresh every
   1.5 seconds. You may cancel a pending or running evaluation.
5. Inspect the model leaderboard and expand individual prompts to compare the
   expected answer with each model output.

The frontend never receives `GROQ_API_KEY`; the browser calls the authenticated
backend, and only the backend worker communicates with GroqCloud. A provider
failure is shown on its individual task row and does not hide successful model
results from the same run.

Create a project from PowerShell:

```powershell
$project = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/projects `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{"name":"Groq comparison","description":"Qwen vs GPT-OSS"}'

$project.id
```

Successful creates return `201`, successful deletes return `204`, missing
resources return `404`, duplicate unique values return `409`, and invalid
request bodies return `422`.

## Running an Evaluation through the API

After creating a project, dataset items, and variants, start a persisted run:

```powershell
$body = @{
  project_id = $project.id
  dataset_id = $dataset.id
  variant_ids = @($qwen.id, $gptOss.id)
  concurrency = 3
} | ConvertTo-Json

$acceptedRun = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/runs `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body
```

The API immediately returns `202 Accepted` with a `pending` run. Read progress
and results with:

- `GET /api/v1/runs?project_id={project_id}`
- `GET /api/v1/runs/{run_id}`
- `GET /api/v1/runs/{run_id}/results?offset=0&limit=50`
- `POST /api/v1/runs/{run_id}/cancel`

`total_tasks` is the number of dataset-item/model pairs. `completed_tasks`
increases after each result is safely committed, so clients can calculate
progress as `completed_tasks / total_tasks`. Individual provider errors are
stored in their results and do not fail the run. Unexpected orchestration or
persistence errors mark the run as `failed`.

## Redis and Celery Worker

The default `TASK_BACKEND=inprocess` remains convenient for development. To run
evaluations in a separate durable worker, start Redis:

```powershell
docker compose -f compose.redis.yaml up -d
docker exec llm-eval-redis redis-cli ping
```

The second command should print `PONG`. The Compose service enables Redis AOF
persistence and stores data in the `llm-eval-redis-data` volume.

Switch the scheduler in `.env`:

```dotenv
TASK_BACKEND=celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

Run the API and worker in separate PowerShell windows:

```powershell
python -m uvicorn backend.main:app --reload
```

```powershell
python -m celery -A backend.worker.celery_app:celery_app `
  worker --loglevel=INFO --pool=solo
```

`--pool=solo` is the predictable development option on Windows. The worker
handles one evaluation run at a time, while each run still performs its model
requests concurrently through the existing asyncio semaphore. Linux workers
can normally use Celery's default prefork pool.

Celery uses late acknowledgement, requeues work when a worker process is lost,
and reserves one long-running task per worker slot. A redelivered task reads
existing PostgreSQL results and evaluates only missing item/model pairs.
Cancellation is cooperative: pending Celery messages are revoked, and a running
worker stops after it observes the database status change.

See the official [Celery configuration](https://docs.celeryq.dev/en/stable/userguide/configuration.html),
[Celery concurrency guide](https://docs.celeryq.dev/en/main/userguide/concurrency/),
and [Redis Docker guide](https://redis.io/tutorials/operate/orchestration/docker/)
for production considerations.

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

Tests inject mocked completion functions into `LiteLLMProvider` and the run API.
Backend integration tests use a temporary SQLite database and cover registration,
login, expired tokens, protected routes, and cross-user isolation. They do not
read your API key, send requests to GroqCloud, or modify PostgreSQL.

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
├── alembic/
│   └── versions/
├── backend/
│   ├── api/
│   ├── db/
│   ├── services/
│   ├── worker/
│   ├── config.py
│   ├── security.py
│   └── main.py
├── evals/
│   ├── datasets/
│   │   └── questions.jsonl
│   ├── dataset.py
│   ├── metrics.py
│   ├── models.py
│   ├── providers.py
│   ├── run.py
│   └── runner.py
├── frontend/
│   ├── app/
│   │   ├── api.ts
│   │   ├── dashboard.tsx
│   │   ├── evaluation-workspace.tsx
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── public/
│   ├── tests/
│   ├── .env.example
│   └── package.json
├── artifacts/
├── tests/
├── .env.example
├── compose.redis.yaml
├── .gitignore
├── pyproject.toml
└── README.md
```

## Current Scope

The asynchronous CLI, authenticated CRUD API, persisted API-managed runs, and
the core frontend experiment workflow are usable today. The backend includes configuration,
FastAPI, PostgreSQL migrations, validation, per-user ownership, selectable
in-process or Redis/Celery execution, progress, cancellation, resumable
delivery, summaries, and result history. The frontend includes authentication,
real overview statistics, projects, recent runs, project creation, project
workspaces, full dataset/test-case management, atomic file import, model-variant
management, evaluation launch, live progress and cancellation, and detailed
result comparison.

Refresh tokens, password recovery, email verification, production Redis
security, model-catalog discovery, richer visual analytics, and full
observability remain future stages.
