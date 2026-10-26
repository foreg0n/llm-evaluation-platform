# Evalflow User and Developer Guide

[Back to the project overview](../README.md)

This guide covers installation, provider credentials, datasets, authentication,
evaluation runs, API and CLI workflows, observability, and production
operations. For the shortest path to a first run, use the
[Docker quick start](../README.md#quick-start) and
[five-minute demo](DEMO.md).

Commands run from the repository root unless a block explicitly changes into
`frontend`. Replace example account details and environment placeholders
before using them.

## Contents

- [Development approach](#development-approach)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Provider API keys](#provider-api-keys)
- [Starting the backend](#starting-the-backend)
- [Running the full stack with Docker](#running-the-full-stack-with-docker)
- [Observability](#observability)
- [Starting the frontend](#starting-the-frontend)
- [Authentication](#authentication)
- [CRUD API and dataset import](#crud-api)
- [Running evaluations: frontend, API, workers, and CLI](#running-evaluations)
- [Testing and continuous integration](#testing-and-continuous-integration)
- [Production releases and deployment](#production-releases-and-deployment)
- [Dataset format, metrics, and architecture](#dataset-format-metrics-and-architecture)
- [Project structure](#project-structure)
- [Current scope](#current-scope)

## Development Approach

Evalflow is a personal learning and portfolio project developed with AI
assistance across the backend, evaluation core, and frontend. The author
defined requirements and visual direction, reviewed and adapted the code,
integrated the components, and tested the application.

## Features

**Evaluation core**

- Real multi-provider calls through LiteLLM: Groq, OpenAI, Anthropic, Gemini,
  OpenRouter, Mistral, DeepSeek, xAI, Cohere, Together AI, Fireworks AI,
  Perplexity, Cerebras, SambaNova, and custom OpenAI-compatible endpoints
  (metadata/link-local URLs blocked; local Ollama and private networks allowed)
- Per-user BYOK credentials encrypted at rest (Fernet), with live model
  discovery, caching, and manual model-ID fallback
- Async runner with configurable concurrency, timeouts, bounded exponential
  retries, and error isolation (one failure never stops a run)
- Exact match, normalized exact match, and keyword metrics, plus latency,
  tokens, estimated cost, and retries per request
- JSONL datasets with Pydantic validation, Rich terminal summary, JSON report,
  network-free tests with mocked providers

**Backend and auth**

- Async SQLAlchemy + Alembic; versioned CRUD API with per-user data isolation
- Runs persisted in PostgreSQL: `202 Accepted` scheduling, progress polling,
  cancellation; in-process or Redis/Celery execution
- Argon2 passwords, short-lived JWTs, rotating hashed refresh sessions
  (HttpOnly cookie, reuse detection), email verification, password recovery,
  in-memory or Redis rate limiting

**Frontend**

- Responsive React UI: auth, dashboard, project workspaces, dataset/test-case
  CRUD, atomic JSON/JSONL/NDJSON import, model-variant management
- Live run progress and cancellation, leaderboard, live charts, server-side
  result filtering/sorting/pagination, run comparison, JSON/CSV export

**Operations**

- Structured JSON logs with request correlation, Prometheus metrics, `/ready`,
  Grafana/Tempo stack with alerts, optional OpenTelemetry and Sentry
- GitHub Actions CI, Ruff, npm audit, Dependabot
- Non-root Docker images, one-command Compose, hardened production stack with
  automatic HTTPS (Caddy)
- Tag-driven multi-arch GHCR releases (provenance + SBOM), protected SSH
  deployments with pre-deploy backup and health gates
- Encrypted off-site PostgreSQL backups with automated restore drills

## Requirements

| Workflow | Requirements |
| --- | --- |
| Docker full stack | Docker Desktop with Linux containers, or Docker Engine with Compose |
| CLI | Python 3.12+ and a Groq API key |
| Local API and frontend | Python 3.12+, Node.js 22.13+, npm, and PostgreSQL |
| Celery worker | Redis and a running worker, or the Docker full stack |

An API key is required for real provider calls. The web app supports multiple
providers; the CLI currently configures Groq-hosted models. Provider
availability and account permissions determine which model IDs you can use.

## Demo and Documentation

Start the full stack, import
[`examples/portfolio-benchmark.json`](../examples/portfolio-benchmark.json) (15
deterministic cases, no credentials) into a project, and compare two real model
variants. Real runs consume provider credits; there is no fake-model path.

Docs: [Demo guide](DEMO.md) · [Deployment](../DEPLOYMENT.md) ·
[Release checklist](../RELEASE_CHECKLIST.md) · [Changelog](../CHANGELOG.md) ·
[Contributing](../CONTRIBUTING.md) · [Security](../SECURITY.md)

## Installation

```bash
git clone https://github.com/foreg0n/llm-evaluation-platform.git
cd llm-evaluation-platform
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Provider API Keys

The web app uses per-user bring-your-own-key credentials. Open **AI
Providers**, choose a provider, save its key, and attach the saved credential
to a model variant.

Keys are encrypted server-side before database storage. Credential responses
return metadata and a short hint instead of the saved plaintext key. The
backend uses the key when loading a live model catalog, testing a connection,
or evaluating prompts. Celery task messages contain the run ID rather than
provider credentials.

Selecting a credential in the model editor loads its model list. IDs are
normalized for LiteLLM and cached for five minutes by default. **Refresh
models** bypasses the cache. If live discovery is unavailable, the UI falls
back to LiteLLM's catalog or manual model-ID entry. A catalog listing does
not guarantee that every model is enabled for the account.

Use **Custom OpenAI-compatible** for another gateway or local server. The URL
validator rejects protected metadata and link-local targets while permitting
local Ollama and private-network endpoints. Use HTTPS for remote services.
When Evalflow runs in Docker, `localhost` inside the container refers to that
container; use a reachable service hostname or `host.docker.internal` for a
provider running on a Docker Desktop host.

For a new installation, create a local environment file.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

Keep an existing installation's environment file and encryption key. The CLI
reads `GROQ_API_KEY` from the root `.env`. Create a key in the
[GroqCloud Console](https://console.groq.com/keys) and set:

```dotenv
GROQ_API_KEY=your-secret-groq-key
```

For web evaluations, saved user credentials can be used without configuring
this server-side Groq fallback. Environment files are Git-ignored.

## Starting the Backend

Use the virtual environment and development dependencies from
[Installation](#installation). Create a PostgreSQL database and configure the
root `.env`. The password in `DATABASE_URL` must match the database user:

```dotenv
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_DATABASE_PASSWORD@localhost:5432/llm_evaluation
DATABASE_ECHO=false
AUTH_SECRET_KEY=replace-with-64-random-hex-characters
CREDENTIAL_ENCRYPTION_KEY=replace-with-a-generated-fernet-key
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=30
REFRESH_COOKIE_SECURE=false
AUTH_RATE_LIMIT_BACKEND=memory
EMAIL_BACKEND=console
FRONTEND_PUBLIC_URL=http://localhost:3000
```

Generate actual values for `AUTH_SECRET_KEY` and
`CREDENTIAL_ENCRYPTION_KEY`, in that order, and replace the placeholders:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

JWTs are signed, not encrypted. Retain the Fernet key with your configuration
backups: replacing it makes existing saved provider credentials unreadable.

Apply migrations and start the API:

```bash
alembic upgrade head
python -m uvicorn backend.main:app --reload
```

The API runs at `http://127.0.0.1:8000`, with interactive documentation at
`http://127.0.0.1:8000/docs`.

For installations upgraded from before authentication, migration `0003`
assigns old projects to the inactive `legacy-import@local.invalid` account.
A database operator can explicitly reassign them to a registered user. This
is a migration placeholder, not a sign-in or admin account. Later migrations
add provider credentials, refresh sessions, account recovery, and pagination
indexes.

## Running the Full Stack with Docker

Follow the [Docker quick start](../README.md#quick-start) to create `.env`
and generate the required database password, auth secret, and Fernet key.
For an existing installation, preserve those values.

`compose.yaml` starts PostgreSQL, Redis, a one-shot Alembic migration job,
FastAPI, a Celery worker, and the built frontend. These values select local
HTTP and console email delivery:

```dotenv
REFRESH_COOKIE_SECURE=false
EMAIL_BACKEND=console
FRONTEND_PUBLIC_URL=http://localhost:3000
```

With ports `3000`, `5432`, `6379`, `8000`, and `9808` free:

```powershell
docker compose up -d --build
docker compose ps -a
docker compose logs -f migrate api worker frontend
```

The migration container should finish with exit code `0`. The API, worker,
frontend, PostgreSQL, and Redis should stay running.

| Service | Local URL |
| --- | --- |
| Frontend | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| API readiness | http://localhost:8000/ready |
| API metrics | http://localhost:8000/metrics |
| Worker metrics | http://localhost:9808/metrics |

Ports bind to `127.0.0.1`, and persistent data uses named volumes. The
application images run as non-root users.

`PUBLIC_API_URL` is embedded into the frontend at build time. After changing
it in `.env`, rebuild and recreate the frontend:

```powershell
docker compose build frontend
docker compose up -d frontend
```

Stop the stack with `docker compose down`. Named volumes are retained;
adding `--volumes` deletes their stored database and queue data.

## Observability

**Logs.** One JSON object per line with method, path, status, duration, and
`request_id` (plus `run_id`, `trace_id`, `span_id` when available). Clients may
send `X-Request-ID` (letters, digits, `.`, `_`, `-`, ≤128 chars); otherwise a
UUID is generated and returned. Set `LOG_LEVEL` and `LOG_FORMAT` (`json` or
`text`). Request bodies, auth headers, passwords, and API keys are excluded from
application logs. With `EMAIL_BACKEND=console`, local logs intentionally
include one-time verification and recovery links.

**Metrics and readiness.** `GET /metrics` exposes HTTP, evaluation-run,
readiness, and Celery metrics (route templates as labels, so cardinality stays
bounded). `GET /ready` is stricter than `/health`: it returns `503` if
PostgreSQL or, with `TASK_BACKEND=celery`, Redis is unavailable. The worker has
its own listener:

```dotenv
READINESS_TIMEOUT_SECONDS=1
CELERY_METRICS_ENABLED=true
CELERY_METRICS_HOST=127.0.0.1
CELERY_METRICS_PORT=9808
```

Bind to `0.0.0.0` only in a private network. For Linux prefork workers set
`PROMETHEUS_MULTIPROC_DIR` to an empty directory before startup.

**Prometheus, Grafana, Tempo.** With the API running on `8000`:

```powershell
docker compose -f compose.observability.yaml up -d
```

Grafana `http://localhost:3001`, Prometheus `http://localhost:9090`
(`/targets`, `/alerts`), Tempo `http://localhost:3200/ready`. Grafana
provisions the `Evalflow / Platform Overview` dashboard and both datasources;
change `GRAFANA_ADMIN_PASSWORD` in `.env`. Seven alert rules cover down
targets, failed dependencies, HTTP errors/latency, and failed runs/tasks;
notifications need an Alertmanager. With `TASK_BACKEND=inprocess` the worker
target is intentionally down. For container traces, set `TRACING_ENABLED=true`
and keep `CONTAINER_OTEL_ENDPOINT=http://host.docker.internal:4318/v1/traces`.

**Tracing (OpenTelemetry).** Off by default:

```dotenv
TRACING_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318/v1/traces
OTEL_EXPORT_TIMEOUT_SECONDS=5
OTEL_TRACE_SAMPLE_RATIO=1.0
```

W3C context travels through Redis into Celery, so a run appears as one trace.
In Grafana **Explore → Evalflow Tempo**, filter by `service.name`
(`llm-evaluation-api` / `llm-evaluation-worker`). Use a lower sample ratio in
production. Spans never store bodies, keys, prompts, or outputs.

**Sentry.** Off by default; enabling it without a DSN fails at startup:

```dotenv
SENTRY_ENABLED=true
SENTRY_DSN=https://public-key@your-sentry-host/project-id
SENTRY_ERROR_SAMPLE_RATE=1.0
```

Never commit a real DSN. Unhandled API/worker failures and persisted-run
failures are tagged with `request_id`, `run_id`, `task_id`. PII, bodies, cookies,
query strings, and auth headers are scrubbed; Sentry tracing is off so
OpenTelemetry remains the only tracing layer.

## Starting the Frontend

With the local backend running, open another terminal.

Windows PowerShell:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm.cmd ci
npm.cmd run dev
```

macOS / Linux:

```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

Open `http://localhost:3000`. The frontend reads `NEXT_PUBLIC_API_URL`
(default `http://127.0.0.1:8000`); for a different frontend origin, add it to
`CORS_ORIGINS` in the root `.env` and restart FastAPI. Use a consistent
hostname for the frontend and browser-facing API URL when relying on
SameSite cookies, for example `localhost` for both.

The access token lives in memory and the refresh token in an HttpOnly
SameSite cookie. Concurrent requests share one refresh request and retry
once. Use `REFRESH_COOKIE_SECURE=true` behind HTTPS. The `npm.cmd` commands
avoid PowerShell blocking the `npm.ps1` wrapper.

## Authentication

Register your own account; there is no default admin login or password.
Email verification is enabled by default. With console delivery, use the link
printed by the API; no real email is sent. The login form also provides a
password recovery flow.

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/auth/register `
  -ContentType "application/json" `
  -Body '{"email":"you@example.com","password":"choose-a-long-password"}'

# Open the verification link (SMTP, or API logs with EMAIL_BACKEND=console)

$login = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/auth/login `
  -ContentType "application/json" `
  -Body '{"email":"you@example.com","password":"choose-a-long-password"}'
$headers = @{ Authorization = "Bearer $($login.access_token)" }
```

Endpoints under `/api/v1/auth/`: `register`, `login`, `token` (OAuth2 form for
Swagger), `refresh`, `logout`, `logout-all`, `email-verification/request|confirm`,
`password-reset/request|confirm`, and `me`. Everything except the
registration/login/refresh/logout and request/confirm flows requires a bearer
token, and users only see their own data.

- **Rate limiting:** failures are limited per hashed client/account identifier
  (in-memory locally, Redis in Compose); blocked requests get `429` +
  `Retry-After`.
- **Refresh tokens:** opaque, stored as SHA-256 hashes, rotated on use;
  replaying a rotated token revokes the whole family.
- **Email tokens:** single-use, hashed, expire after 24 h (verification) or
  30 min (recovery; a reset revokes refresh sessions). Previously issued access
  tokens remain valid until their short expiration. Request endpoints always
  return the same `202`, and links keep the token in the URL fragment.
- **Email delivery:** `EMAIL_BACKEND=console` locally; in production use
  `smtp` with `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
  `SMTP_STARTTLS`, `EMAIL_FROM_ADDRESS`, and an HTTPS `FRONTEND_PUBLIC_URL`.

## CRUD API

All endpoints use the `/api/v1` prefix; collections support `offset` and
`limit` (max 100).

| Resource | Create and list | Read, update, delete |
| --- | --- | --- |
| Projects | `POST/GET /projects` | `/projects/{project_id}` |
| Datasets | `POST/GET /projects/{project_id}/datasets` | `/datasets/{dataset_id}` |
| Dataset items | `POST/GET /datasets/{dataset_id}/items` | `/dataset-items/{item_id}` |
| Variants | `POST/GET /projects/{project_id}/variants` | `/variants/{variant_id}` |
| Provider credentials | `POST/GET /provider-credentials` | `/provider-credentials/{credential_id}` |

Also: `GET /providers/catalog`; `POST /provider-credentials/{id}/test` (one
minimal real request; body holds the LiteLLM model ID);
`GET /provider-credentials/{id}/models[?refresh=true]` (IDs only, never the
key). Deleting a credential attached to a variant returns `409`. Status codes:
`201` create, `204` delete, `404` missing, `409` duplicate, `422` invalid body.

**Dataset import.** **Import file** accepts `.jsonl`/`.ndjson` (one case per
line) or `.json` (an array, a single case, or an object with `name`,
`description`, `items`):

```json
{"id":"capital-france","input":"What is the capital of France?","expected_output":"Paris","keywords":["Paris"]}
```

`external_id` may replace `id`. Files must be UTF-8, ≤ 5 MB, hold 1–1,000
cases, and use unique IDs; the whole file is validated before one transaction
commits, so there are no partial imports. Endpoint:
`POST /projects/{project_id}/datasets/import`. Items load 50 at a time via
`GET /datasets/{dataset_id}/items/page` (exact total + `has_more`).

## Running Evaluations

### From the frontend

1. Open a project and import or create a dataset.
2. In **AI Providers**, add and test credentials.
3. In **Models**, add variants with LiteLLM model IDs and credentials.
4. In **Evaluation runs**, pick a dataset and models, set concurrency, then
   **Start evaluation** (progress refreshes every 1.5 s; you can cancel).
5. Inspect the leaderboard and expand prompts to compare answers.

Saved plaintext keys are excluded from API responses. The backend decrypts
them for live model discovery, connection tests, and evaluation requests;
Celery messages carry only the run ID. A provider
failure appears on its own task row without hiding other results.

- **Live charts:** quality, latency, tokens, cost, and errors per model, with
  the best value highlighted; models without results are excluded.
- **Results:** search by prompt, filter by model or status (success, error,
  quality below 67%), sort by quality/latency/tokens. Done in PostgreSQL via
  `GET /runs/{run_id}/results/page` (25/50/100 rows); polling fetches only
  status and SQL-computed summaries.
- **Comparison:** two completed runs show deltas (improved/regressed/unchanged)
  overall and per model, with warnings when datasets or model sets differ.
- **Export:** runs to JSON or CSV (one row per response), comparisons to JSON or
  long-format CSV; Excel-friendly (UTF-8 BOM, formula prefixes neutralized).
  Comparison and export never call a provider.

### Through the API

This PowerShell example creates a project, one test case, a model variant,
and a run. First register and verify an account, then save a Groq credential
through **AI Providers**. Run the block from the repository root and replace
the example login details. It uses a saved credential without putting a
provider API key into the script:

```powershell
$baseUrl = "http://127.0.0.1:8000/api/v1"
$login = Invoke-RestMethod -Method Post -Uri "$baseUrl/auth/login" `
  -ContentType "application/json" `
  -Body '{"email":"you@example.com","password":"choose-a-long-password"}'
$headers = @{ Authorization = "Bearer $($login.access_token)" }

$projectBody = @{
  name = "API demo $(Get-Date -Format yyyyMMdd-HHmmss)"
  description = "A small evaluation created through the API"
} | ConvertTo-Json
$project = Invoke-RestMethod -Method Post -Uri "$baseUrl/projects" `
  -Headers $headers -ContentType "application/json" -Body $projectBody

$dataset = Invoke-RestMethod -Method Post `
  -Uri "$baseUrl/projects/$($project.id)/datasets" `
  -Headers $headers -ContentType "application/json" `
  -Body '{"name":"API smoke test"}'

$itemBody = @{
  external_id = "capital-france"
  input = "What is the capital of France? Answer with one word."
  expected_output = "Paris"
  keywords = @("Paris")
} | ConvertTo-Json
$item = Invoke-RestMethod -Method Post `
  -Uri "$baseUrl/datasets/$($dataset.id)/items" `
  -Headers $headers -ContentType "application/json" -Body $itemBody

$credentials = Invoke-RestMethod -Uri "$baseUrl/provider-credentials" -Headers $headers
$credential = $credentials | Where-Object { $_.provider -eq "groq" } | Select-Object -First 1
if (-not $credential) { throw "Save a Groq credential in AI Providers first." }

$modelCatalog = Invoke-RestMethod `
  -Uri "$baseUrl/provider-credentials/$($credential.id)/models" -Headers $headers
$modelCatalog.models | Select-Object id, label | Format-Table
$modelId = Read-Host "Enter a text-generation model ID, including the groq/ prefix"

$variantBody = @{
  name = "Groq baseline"
  provider = "litellm"
  credential_id = $credential.id
  model = $modelId
  temperature = 0
  max_tokens = 1024
  timeout_seconds = 60
  max_retries = 2
} | ConvertTo-Json
$variant = Invoke-RestMethod -Method Post `
  -Uri "$baseUrl/projects/$($project.id)/variants" `
  -Headers $headers -ContentType "application/json" -Body $variantBody

$runBody = @{
  project_id = $project.id
  dataset_id = $dataset.id
  variant_ids = @($variant.id)
  concurrency = 2
} | ConvertTo-Json
$acceptedRun = Invoke-RestMethod -Method Post -Uri "$baseUrl/runs" `
  -Headers $headers -ContentType "application/json" -Body $runBody
$acceptedRun
```

The API returns `202 Accepted` with a `pending` run. Track it with
`GET /api/v1/runs/{run_id}` and fetch results with
`GET /api/v1/runs/{run_id}/results/page`. To cancel, use
`POST /api/v1/runs/{run_id}/cancel`. All requests require the same bearer
header.

`total_tasks` is the number of item/model pairs, and `completed_tasks`
grows as results commit. Provider errors are stored per result; unexpected
orchestration or persistence errors mark the run `failed`. Create additional
variants and include their IDs in `variant_ids` to compare models.

### Redis and Celery worker

`TASK_BACKEND=inprocess` (default) suits development. For a durable worker:

```powershell
docker compose -f compose.redis.yaml up -d
docker exec llm-eval-redis redis-cli ping   # expect PONG
```

```dotenv
TASK_BACKEND=celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

```powershell
python -m uvicorn backend.main:app --reload
python -m celery -A backend.worker.celery_app:celery_app worker --loglevel=INFO --pool=solo
```

`--pool=solo` is the predictable choice on Windows; Linux can use prefork. The
worker handles one run at a time (requests within it stay concurrent). Late
acknowledgement requeues work if a worker dies, and a redelivered task evaluates
only missing item/model pairs. Cancellation is cooperative: pending messages are
revoked, and a running worker stops after seeing the status change.

### From the CLI

The CLI uses `GROQ_API_KEY` from the root `.env` and reads the bundled
five-item JSONL dataset. Select a text-generation model enabled for your
Groq account. The `groq/` prefix is optional in this CLI.

Windows PowerShell:

```powershell
$groqModel = Read-Host "Enter your Groq text-generation model ID"
python -m evals.run --model $groqModel --concurrency 2
```

macOS / Linux:

```bash
read -r -p "Enter your Groq text-generation model ID: " groq_model
python -m evals.run --model "$groq_model" --concurrency 2
```

Repeat `--model` to compare models. Replace the example identifiers below
with values available to your account:

```bash
python -m evals.run --model YOUR_FIRST_GROQ_MODEL_ID --model YOUR_SECOND_GROQ_MODEL_ID --concurrency 2
```

The default concurrency is `3`. Other options include `--temperature`,
`--max-tokens`, `--system-prompt`, `--timeout`, `--max-retries`,
`--dataset`, and `--output`:

```bash
python -m evals.run --help
```

Without an explicit `--model`, the runner uses the model IDs currently
defined in `DEFAULT_GROQ_MODELS` in `evals/run.py`. These are repository
defaults, not a guarantee that the provider still offers them.

A Rich summary is printed and the full JSON report goes to
`artifacts/results.json` by default. It contains responses, metrics,
latency, tokens, estimated cost when available, retries, and errors. The
CLI saves local reports; use the web app or API for persisted workspace runs.

## Testing and Continuous Integration

```bash
python -m pytest
python -m ruff check backend evals tests scripts
python scripts/release_audit.py
```

Tests use mocked completion functions and a temporary SQLite database, covering
auth, verification, recovery, token expiry/reuse, refresh rotation, rate
limiting, encrypted credentials, protected routes, and cross-user isolation.
They never touch real keys, SMTP, Redis, provider APIs, or PostgreSQL.

`.github/workflows/ci.yml` runs on pushes to `main`, pull requests, manual
dispatch, and as the release quality gate, with only `contents: read`, no real
secrets, and `pull_request` (not `pull_request_target`). Jobs:

1. **Backend:** compile, Ruff, release audit, pytest, and the Alembic SQL chain.
2. **Frontend:** locked dependency installation, ESLint, production dependency
   audit, Vinext build, and server-render/security tests.
3. **Configuration:** validate shell scripts and parse all Compose files with
   placeholder values.
4. **Backup/restore drill:** migrate a fresh PostgreSQL, take an encrypted
   restic snapshot, restore it into an isolated target, verify schema and tables.
5. **Container builds:** after the above pass, build all three images without
   pushing.

Newer commits cancel concurrent runs on a branch. Dependabot checks Actions,
pip, npm, and Dockerfiles weekly.

## Production Releases and Deployment

Pushing a semantic tag such as `v0.37.0` starts `release.yml`: it reruns the CI
gate, builds Linux AMD64/ARM64 API, frontend, and backup images, and publishes
exact-version, minor-version, and `latest` tags to GHCR with provenance and an
SBOM (needs only `contents: read` and `packages: write`).

The manual **Deploy production** workflow then deploys an exact tag. It requires
the confirmation `deploy-production`, is serialized, and enters the GitHub
`production` Environment before any secret is available (configure a required
reviewer and tag/branch restrictions). It verifies the GHCR manifests, pins the
server's SSH host key, and sends only the release bundle and a protected env file.

`compose.production.yaml` pulls configured version-tagged images, forces secure cookies and
Redis rate limiting, requires all secrets, and exposes only Caddy on `80`/`443`
(automatic certificates, HTTP→HTTPS, security headers, `/api/*` and `/health`
routed to FastAPI). `/ready`, `/metrics`, API docs, databases, and worker
metrics stay private.

`infra/provision-ubuntu.sh` prepares a fresh Ubuntu host (Docker, deploy
account, fail2ban, unattended updates). The deploy script validates the new
environment first, backs up the database on upgrades, locks concurrent deploys,
waits for migrations and health checks, and verifies public HTTPS. The previous
env file is kept for operator-led rollback; migrations are forward-only. Copy
`.env.production.example`, replace every placeholder, point DNS at the server,
and follow [DEPLOYMENT.md](../DEPLOYMENT.md).

### Encrypted Backups and Restore Drills

A non-root backup image (PostgreSQL 17 client + restic 0.19.1) runs a
custom-format `pg_dump` on startup and every 24 h into an encrypted restic
repository with daily/weekly/monthly retention. Failed attempts retry after 5
minutes without stopping other services. Configure in `.env.production`:

```dotenv
EVALFLOW_BACKUP_IMAGE=ghcr.io/foreg0n/llm-evaluation-platform-backup:0.37.0
RESTIC_REPOSITORY=s3:https://s3.example.com/evalflow-production/postgres
RESTIC_PASSWORD=replace-with-an-independent-encryption-password
AWS_ACCESS_KEY_ID=replace-with-object-storage-access-key
AWS_SECRET_ACCESS_KEY=replace-with-object-storage-secret-key
AWS_DEFAULT_REGION=auto
BACKUP_KEEP_DAILY=7
BACKUP_KEEP_WEEKLY=5
BACKUP_KEEP_MONTHLY=12
```

Store `RESTIC_PASSWORD` separately from the bucket, and keep
`CREDENTIAL_ENCRYPTION_KEY` in a secret manager: backups do not contain the
Fernet key needed to decrypt BYOK values.

```bash
compose_prod() {
  docker compose --env-file .env.production -f compose.production.yaml "$@"
}
compose_prod exec -T backup /opt/evalflow-backup/healthcheck.sh
compose_prod run --rm --no-deps backup backup
compose_prod run --rm --no-deps backup restic snapshots --tag evalflow-postgres
```

The restore profile never touches the live database: it restores the latest
snapshot into a temporary PostgreSQL container, runs `pg_restore
--exit-on-error`, reads the Alembic version, and enforces a minimum table count.

```bash
compose_prod --profile restore up --abort-on-container-exit \
  --exit-code-from restore-drill restore-drill
compose_prod --profile restore rm -f restore-drill restore-postgres
```

CI runs the same sequence via `compose.backup-drill.yaml`. See
[DEPLOYMENT.md](../DEPLOYMENT.md) for retention and recovery.

## Dataset Format, Metrics, and Architecture

Each line of `evals/datasets/questions.jsonl` is a JSON object:

```json
{"id": "1", "input": "What is the capital of France?", "expected_output": "Paris", "keywords": ["Paris"]}
```

`id` is a unique identifier, `input` the prompt, `expected_output` the
reference answer, and `keywords` the terms a valid answer should contain.

| Metric | Description |
| --- | --- |
| Exact match | Compares lowercased, trimmed strings |
| Normalized exact match | Also removes punctuation and collapses whitespace |
| Keyword score | Fraction of required keywords found |

Overall quality is the mean of the three scores; individual values stay in the
JSON report. These are reference-answer heuristics, not semantic similarity or
an LLM judge. Estimated cost is available only when the provider integration
can determine pricing; it is not a billing statement.

The runner depends on a small provider interface:

```python
class AsyncLLMProvider(Protocol):
    async def generate(self, prompt: str, variant: Variant) -> GenerationResponse:
        ...
```

`LiteLLMProvider` implements it with `litellm.acompletion`, mapping completions
(including token and cost data) into `GenerationResponse`. The runner creates
one task per item/model pair and limits concurrency with an `asyncio.Semaphore`.
Connection, timeout, rate-limit, server, and invalid-response errors use bounded
exponential backoff; authentication and validation errors fail immediately. In
both cases the error is recorded and the run continues.

## Project Structure

```text
llm-evaluation-platform/
├── alembic/versions/
├── backend/            # api/ db/ services/ worker/ + config, security, metrics,
│                       # tracing, observability, error_monitoring,
│                       # credential_security, provider_catalog, main
├── deploy/             # backup/ (scripts, Dockerfile), scripts/deploy-production.sh, Caddyfile
├── docs/               # GUIDE.md, DEMO.md
├── evals/              # datasets/questions.jsonl, dataset, metrics, models,
│                       # providers, run, runner
├── examples/portfolio-benchmark.json
├── frontend/           # app/ (api.ts, dashboard.tsx, evaluation-workspace.tsx,
│                       # provider-workspace.tsx, layout, page, globals.css),
│                       # public/, tests/, Dockerfile, .env.example, package.json
├── infra/              # provision-ubuntu.sh, README.md
├── observability/      # grafana/ (dashboards, provisioning), prometheus/
│                       # (alerts.yml, prometheus.yml), tempo/tempo.yml
├── scripts/release_audit.py
├── tests/  artifacts/
├── compose.yaml, compose.production.yaml, compose.observability.yaml,
│   compose.redis.yaml, compose.backup-drill.yaml
├── Dockerfile, pyproject.toml, .env.example, .env.production.example
└── CHANGELOG.md, CONTRIBUTING.md, RELEASE_CHECKLIST.md, SECURITY.md, README.md
```

## Current Scope

The CLI, authenticated CRUD API, persisted runs, and the full frontend workflow
(auth, BYOK credentials with model discovery, datasets with atomic import,
model variants, live runs, charts, filtering, comparison, export) are usable
today, alongside the observability stack, hardened HTTPS production topology,
tagged GHCR releases, protected deployments, and encrypted backups with verified
restore drills.

Semantic similarity, LLM-as-a-Judge, durable
notification delivery, a shared result cache, and public cloud deployment are
optional post-v1.0 extensions, not release requirements for this personal
GitHub project.
