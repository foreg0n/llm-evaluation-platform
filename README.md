# LLM Evaluation Platform

[![CI](https://github.com/foreg0n/llm-evaluation-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/foreg0n/llm-evaluation-platform/actions/workflows/ci.yml)

A full-stack evaluation platform for comparing real language models across
multiple AI providers. It combines an asynchronous CLI, a FastAPI and
PostgreSQL backend, and a dark analytics frontend for everyday experiment
management.

## Development Approach

The backend and evaluation core were designed and implemented by the project
author. This includes the provider architecture, asynchronous runner, metrics,
FastAPI application, PostgreSQL persistence, authentication, Celery/Redis task
execution, error handling, and automated tests.

The frontend was developed with assistance from AI coding tools. The project
author defined the product requirements, selected the visual direction,
reviewed the generated code, connected it to the backend, and tested the
complete workflow.

## Features

- Real multi-provider API calls through LiteLLM
- Per-user BYOK credentials encrypted at rest with Fernet
- Built-in setup for Groq, OpenAI, Anthropic, Gemini, OpenRouter, Mistral,
  DeepSeek, xAI, Cohere, Together AI, Fireworks AI, Perplexity, Cerebras, and
  SambaNova
- Custom OpenAI-compatible endpoint support
- Credential-scoped live model discovery with caching, safe fallbacks, and
  manual model-ID entry
- Qwen 3.6 27B and GPT-OSS 20B compared in every default run
- Asynchronous requests with configurable concurrency
- A shared provider protocol for clean model integration
- JSONL dataset loading and Pydantic validation
- Exact match, normalized exact match, and keyword coverage metrics
- Per-request latency, token usage, estimated cost, and retry tracking
- Configurable timeouts and bounded exponential-backoff retries
- Error isolation: one failed request does not stop the evaluation run
- Rich terminal summary and a reproducible JSON report
- Network-free tests using mocked provider responses
- FastAPI application with a database-aware health endpoint
- Async SQLAlchemy models and an Alembic migration for experiment history
- Versioned CRUD API for projects, datasets, dataset items, and model variants
- API-managed evaluation runs persisted in PostgreSQL
- Fast `202 Accepted` scheduling, progress polling, and run cancellation
- Argon2 password hashing and short-lived JWT access tokens
- Rotating opaque refresh sessions stored as SHA-256 hashes
- HttpOnly SameSite refresh cookies, logout, logout-all, and reuse detection
- Configurable in-memory or Redis-backed authentication rate limiting
- Required email verification for new accounts with one-time hashed tokens
- Password recovery with expiring links and all-session revocation
- SMTP delivery for deployments and console delivery for local development
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
- Live comparison charts for quality, latency, tokens, cost, and provider errors
- Client-side result search, model/status filters, and metric sorting
- Completed-run comparison with overall and per-model metric deltas
- Browser-side JSON and Excel-friendly CSV exports for runs and comparisons
- Structured JSON logs with HTTP, evaluation-run, and Celery lifecycle events
- End-to-end request correlation through validated `X-Request-ID` values
- Prometheus metrics for HTTP traffic, evaluation runs, readiness, and workers
- Separate database/Redis readiness reporting through `GET /ready`
- Local Prometheus and Grafana stack with persistent named volumes
- Provisioned platform dashboard and alert rules for availability and failures
- Optional OpenTelemetry tracing across FastAPI and Celery through W3C context
- Local Grafana Tempo storage and a provisioned trace-exploration datasource
- Optional privacy-safe Sentry error reporting for FastAPI and Celery failures
- Read-only GitHub Actions CI for backend, frontend, migrations, Compose, and
  production container builds
- Weekly Dependabot updates for GitHub Actions, Python, npm, and Docker
- Production-oriented Docker images and one-command full-stack Compose startup
- Separate hardened production topology with automatic HTTPS through Caddy
- Private database/queue networks and password-authenticated production Redis
- Tag-driven multi-architecture API/frontend/backup releases to GitHub Container Registry
- Build provenance and software bill of materials for published container images
- Encrypted off-site PostgreSQL backups with daily/weekly/monthly retention
- Backup freshness health checks and automated retry scheduling
- Isolated end-to-end restore drills that verify schema and table integrity
- Idempotent Ubuntu VPS bootstrap with official Docker packages and SSH key access
- Protected, serialized production deployments from exact Git tags
- Pinned SSH host identity, pre-deploy backups, migrations, and public health gates

## Requirements

- Python 3.12 or newer
- Node.js 22.13 or newer and npm
- An API key for at least one supported AI provider
- PostgreSQL for the backend API
- Docker Engine with Docker Compose for the containerized full stack

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

## Provider API Keys

The web application uses per-user bring-your-own-key (BYOK) credentials. After
signing in, open **AI Providers**, choose a provider, and save its API key. The
key is encrypted before it reaches PostgreSQL and is never returned to the
browser. Attach the saved credential when creating or editing a model variant.

The built-in catalog includes the most common key-based LiteLLM providers. Use
**Custom OpenAI-compatible** for another service that exposes an OpenAI-style
API, and provide its HTTP(S) base URL. Use HTTPS outside local development. A
credential is sent to a provider only when you explicitly test it or run an
evaluation.

When a saved credential is selected in the model editor, Evalflow asks that
provider for its current model list. The backend decrypts the key only for that
request, normalizes the returned IDs for LiteLLM, and caches the result for five
minutes. **Refresh models** bypasses the cache. If the provider list is
unavailable, the UI falls back to LiteLLM's built-in catalog or lets you enter
any compatible model ID manually; a discovery failure never blocks variant
creation.

The CLI can still use a server-side Groq key. Create one in the
[GroqCloud Console](https://console.groq.com/keys), then copy the environment
template:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS or Linux:

```bash
cp .env.example .env
```

Add the key to `.env`:

```dotenv
GROQ_API_KEY=your-secret-groq-key
```

`GROQ_API_KEY` is optional for web variants that have a saved credential, but
keeps the default CLI workflow and legacy server-environment fallback working.
The `.env` file is ignored by Git. Never commit, publish, or share API keys;
revoke an exposed key immediately in its provider console.

## Starting the Backend

Create a PostgreSQL database, then set its async SQLAlchemy URL in `.env`:

```dotenv
DATABASE_URL=postgresql+asyncpg://postgres:change-me@localhost:5432/llm_evaluation
DATABASE_ECHO=false
AUTH_SECRET_KEY=replace-with-a-random-secret
CREDENTIAL_ENCRYPTION_KEY=replace-with-a-fernet-key
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=30
REFRESH_COOKIE_SECURE=false
AUTH_RATE_LIMIT_BACKEND=memory
```

Generate a strong signing secret instead of typing one manually:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the printed value into `AUTH_SECRET_KEY`. JWT payloads are signed, not
encrypted, so never put passwords, API keys, or other secrets inside them. Use
HTTPS outside local development.

Generate the separate Fernet key used to encrypt provider credentials:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy it into `CREDENTIAL_ENCRYPTION_KEY`. Back it up securely: replacing this
value makes existing saved credentials unreadable. Production startup rejects
the development default.

Create or update the database schema:

```bash
alembic upgrade head
```

Migration `20260815_0003` preserves projects created before authentication by
assigning them to an inactive `legacy-import@local.invalid` account. After you
register, a database administrator may explicitly reassign those projects to
your new user ID; they are never exposed automatically.

Migration `20260824_0004` adds encrypted per-user provider credentials and the
optional credential link on model variants.

Migration `20260824_0005` adds hashed, rotating refresh sessions and their
revocation chain. No plaintext refresh token is stored in PostgreSQL.

Migration `20260825_0006` marks existing users as verified, adds
`email_verified_at`, and creates hashed one-time tokens for email verification
and password recovery. New accounts remain unverified until their link is used.

Start the API from the repository root:

```bash
python -m uvicorn backend.main:app --reload
```

The API is then available at `http://127.0.0.1:8000`, with interactive docs at
`http://127.0.0.1:8000/docs`.

## Running the Full Stack with Docker

The root `compose.yaml` builds and starts PostgreSQL, Redis, a one-shot Alembic
migration job, FastAPI, the Celery worker, and the production frontend. Local
Python, Node.js, PostgreSQL, and Redis installations are not required for this
mode; only Docker and provider credentials are needed.

Create `.env` if it does not exist, then set at least these values:

```dotenv
POSTGRES_PASSWORD=choose-a-long-url-safe-password
AUTH_SECRET_KEY=replace-with-64-random-hex-characters
CREDENTIAL_ENCRYPTION_KEY=replace-with-a-generated-fernet-key
# Keep false only for the localhost HTTP stack; use true behind HTTPS.
REFRESH_COOKIE_SECURE=false
# Optional CLI/server fallback:
GROQ_API_KEY=your-secret-groq-key
```

Generate both application secrets with:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Do not commit `.env`. The Docker build contexts explicitly exclude `.env`,
local virtual environments, `node_modules`, build output, test caches, and
other development files.

Make sure ports `3000`, `5432`, `6379`, `8000`, and `9808` are not already used
by manually started processes or the smaller `compose.redis.yaml` stack. Build
and start the complete application from the repository root:

```powershell
docker compose up -d --build
docker compose ps -a
```

The `migrate` container waits for healthy PostgreSQL, runs
`alembic upgrade head`, and exits successfully. The API and worker start only after that job
completes and Redis is healthy. The frontend then waits for the API readiness
check. Follow startup logs with:

```powershell
docker compose logs -f migrate api worker frontend
```

Open:

- frontend: `http://localhost:3000`;
- API documentation: `http://localhost:8000/docs`;
- readiness: `http://localhost:8000/ready`;
- API metrics: `http://localhost:8000/metrics`;
- worker metrics: `http://localhost:9808/metrics`.

All published ports bind to `127.0.0.1` by default. PostgreSQL and Redis use
persistent named volumes. The API and worker share one non-root Python image;
the frontend runs a minimal Vinext standalone bundle as the non-root Node user.

`PUBLIC_API_URL` is embedded into the browser bundle during image build. If the
API is exposed at a different browser-visible URL, update that value and rebuild
the frontend image:

```powershell
docker compose build frontend
docker compose up -d frontend
```

The optional observability stack remains separate and can run alongside the
application:

```powershell
docker compose -f compose.observability.yaml up -d
```

To export container traces to that local Tempo instance, set
`TRACING_ENABLED=true` and keep `CONTAINER_OTEL_ENDPOINT` pointed at
`http://host.docker.internal:4318/v1/traces`, then recreate the API and worker.
The default application ports should remain unchanged because the provisioned
Prometheus targets scrape host ports `8000` and `9808`.

Stop the application while preserving database and Redis data:

```powershell
docker compose down
```

Adding `-v` removes both named volumes and permanently deletes the containerized
PostgreSQL and Redis data.

### Structured Logging and Request Correlation

The API writes one JSON object per log line by default. Every HTTP completion
event includes the method, path, status code, duration, environment, application
version, and `request_id`. Evaluation execution and Celery task lifecycle events
also carry `run_id` and, when available, the originating request ID. When
OpenTelemetry tracing is enabled, logs emitted inside a span additionally carry
lowercase hexadecimal `trace_id` and `span_id` fields.

```json
{"level":"info","event":"http_request_completed","request_id":"2dc03f54-...","method":"GET","path":"/health","status_code":200,"duration_ms":4.281}
```

Clients may send `X-Request-ID` using letters, numbers, dots, underscores, or
hyphens, up to 128 characters. Missing or unsafe values are replaced with a
UUID. The selected ID is returned in the response header and exposed through
CORS, making a frontend error report easy to match with its backend log line.

Configure logging in `.env`:

```dotenv
LOG_LEVEL=INFO
LOG_FORMAT=json
```

Supported levels are `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`. Set
`LOG_FORMAT=text` for a more compact local-development view. Logs intentionally
exclude request bodies, authorization headers, passwords, and API keys.

### Prometheus Metrics and Readiness

The API exposes process-local Prometheus text metrics at:

```text
GET http://127.0.0.1:8000/metrics
```

The main metric families are:

- `evalflow_http_requests_total` and `evalflow_http_request_duration_seconds`;
- `evalflow_evaluation_runs_total`, in-progress runs, and run duration;
- `evalflow_readiness_checks_total` by component and result;
- Celery task totals, in-progress tasks, and task duration.

HTTP labels use FastAPI route templates such as `/api/v1/runs/{run_id}`, never
raw UUID paths or query strings. This keeps Prometheus label cardinality bounded
as the number of projects and runs grows.

`GET /ready` is stricter than the existing database-aware `/health` check. It
returns `200 ready` when PostgreSQL and the configured execution backend are
usable. With `TASK_BACKEND=inprocess`, the queue is reported as local. With
`TASK_BACKEND=celery`, the endpoint performs a short async Redis broker ping and
returns `503 not_ready` when either PostgreSQL or Redis is unavailable.

```json
{"status":"ready","database":"reachable","task_backend":"celery","broker":"reachable","task_queue":"ready"}
```

The Celery worker starts its own metrics listener, independently from FastAPI:

```text
http://127.0.0.1:9808/metrics
```

Configure both checks and the worker listener in `.env`:

```dotenv
READINESS_TIMEOUT_SECONDS=1
CELERY_METRICS_ENABLED=true
CELERY_METRICS_HOST=127.0.0.1
CELERY_METRICS_PORT=9808
```

The default host keeps metrics local. Bind to `0.0.0.0` only inside a protected
container or private network. For Linux Celery prefork workers, set
`PROMETHEUS_MULTIPROC_DIR` in the process environment before worker startup and
start with an empty directory; the worker endpoint then aggregates child-process
counters and uses live-sum gauges. Windows `--pool=solo` needs no multiprocess
directory.

### Running Prometheus, Grafana, and Tempo

The repository includes a monitoring stack whose metrics, tracing, dashboard,
and alert configuration are kept in Git. Before starting it, run FastAPI on
port `8000`. For complete worker telemetry, also use `TASK_BACKEND=celery`,
start Redis, and run the Celery worker with its metrics listener on port `9808`.

Start Prometheus and Grafana from the repository root:

```powershell
docker compose -f compose.observability.yaml up -d
docker compose -f compose.observability.yaml ps
```

Open these local endpoints:

- Grafana: `http://localhost:3001`
- Prometheus targets: `http://localhost:9090/targets`
- Prometheus alert rules: `http://localhost:9090/alerts`
- Tempo API: `http://localhost:3200/ready`

Grafana automatically loads the `Evalflow / Platform Overview` dashboard, the
Prometheus datasource, and the `Evalflow Tempo` tracing datasource. The initial
login comes from `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD`; change the
example password in `.env` before sharing the machine or exposing the service.
All published web and OTLP ports bind only to localhost by default.

The dashboard tracks API and worker availability, request rate, 5xx ratio, p95
latency, run outcomes and duration, worker task outcomes, active work, and
readiness failures. Seven Prometheus rules cover unavailable targets, failed
dependencies, elevated HTTP errors or latency, and failed runs or Celery tasks.
The rules evaluate in Prometheus; delivering notifications requires adding an
Alertmanager or another notification integration.

If the project uses `TASK_BACKEND=inprocess`, the worker target is intentionally
down because no Celery metrics listener is running. Inspect container logs with:

```powershell
docker compose -f compose.observability.yaml logs -f prometheus grafana tempo
```

Stop the containers without deleting their stored data:

```powershell
docker compose -f compose.observability.yaml down
```

Adding `-v` to the last command also deletes the Prometheus, Grafana, and Tempo
named volumes, including locally retained metrics, traces, and Grafana state.

### Distributed Tracing with OpenTelemetry

Tracing is disabled by default, so missing Tempo infrastructure never prevents
the API, CLI, worker, or tests from starting. To enable local trace export, put
the following values in `.env` before starting FastAPI and the Celery worker:

```dotenv
TRACING_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318/v1/traces
OTEL_EXPORT_TIMEOUT_SECONDS=5
OTEL_TRACE_SAMPLE_RATIO=1.0
```

FastAPI creates server spans for application routes while excluding `/health`,
`/ready`, and `/metrics`. Celery instrumentation injects the standard W3C trace
context into the Redis message and restores it in the worker. Consequently, an
evaluation scheduled by an HTTP request appears as one distributed trace rather
than unrelated API and worker events.

Open Grafana, select **Explore**, and choose **Evalflow Tempo**. Use **Search**
to filter by `service.name`:

- `llm-evaluation-api` for HTTP and Celery publishing spans;
- `llm-evaluation-worker` for task execution spans.

The default `1.0` sample ratio records every local trace. Use a smaller value in
production. Tempo has no built-in authentication in this local setup, so its
HTTP and OTLP receivers remain bound to localhost. Automatic spans do not store
request bodies, passwords, API keys, prompts, or generated model outputs; avoid
putting secrets in URLs or custom span attributes.

### External Error Monitoring with Sentry

Sentry reporting is disabled by default and the application works normally
without a Sentry account. To enable it, create a Sentry Python project, copy its
DSN into the local `.env` file, and restart both FastAPI and the Celery worker:

```dotenv
SENTRY_ENABLED=true
SENTRY_DSN=https://public-key@your-sentry-host/project-id
SENTRY_ERROR_SAMPLE_RATE=1.0
```

Never commit a real DSN to Git. `.env` is ignored, while `.env.example` contains
only an empty placeholder. Setting `SENTRY_ENABLED=true` without a non-empty DSN
fails configuration early instead of silently losing error reports.

The FastAPI and Celery integrations capture unhandled API and worker failures.
Failures handled inside the evaluation executor are captured explicitly because
they are converted into a persisted `failed` run rather than re-raised. Events
are tagged with available `request_id`, `run_id`, and `task_id` correlation IDs,
plus the environment, release, and API/worker service name.

Privacy controls are enforced in code: default PII is disabled, request bodies
and local variables are not collected, cookies and query strings are removed,
authentication and API-key headers are filtered, and known nested secret fields
are replaced before an event leaves the process. Prompts, expected answers,
generated model output, passwords, and Groq API keys are not intentionally sent.

Sentry performance tracing and profiling are disabled. OpenTelemetry and Tempo
remain the single tracing system, preventing duplicate spans and conflicting
trace propagation. Tests force `SENTRY_ENABLED=false` and replace SDK calls with
local fakes, so `pytest` never sends an event to a real Sentry endpoint.

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

The access token stays only in JavaScript module/React memory. The browser
stores an opaque rotating refresh token in an HttpOnly SameSite cookie, so
JavaScript cannot read it. The API client shares one in-flight refresh across
concurrent requests and retries a protected request once after access-token
expiration. Set `REFRESH_COOKIE_SECURE=true` when the application is served
through production HTTPS; keep it `false` only for localhost HTTP.

If the frontend runs on a different origin, add it to the comma-separated
`CORS_ORIGINS` value in the root `.env` file and restart FastAPI.

## Authentication

Register once, verify the email address, then exchange the credentials for a
short-lived bearer token:

```powershell
$user = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/auth/register `
  -ContentType "application/json" `
  -Body '{"email":"you@example.com","password":"choose-a-long-password"}'

# Open the verification URL delivered by SMTP. With EMAIL_BACKEND=console,
# copy it from the API terminal or run: docker compose logs api

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
- `POST /api/v1/auth/refresh` for refresh-token rotation and a new access token
- `POST /api/v1/auth/logout` to revoke the current refresh-session family
- `POST /api/v1/auth/logout-all` to revoke every refresh session for the user
- `POST /api/v1/auth/email-verification/request` to resend a verification link
- `POST /api/v1/auth/email-verification/confirm` to consume that one-time link
- `POST /api/v1/auth/password-reset/request` to request recovery instructions
- `POST /api/v1/auth/password-reset/confirm` to set a new password and revoke
  all existing refresh sessions
- `GET /api/v1/auth/me` for the current account

The health endpoint and registration/login/refresh/logout endpoints are public;
`logout-all`, `me`, and all project, dataset, item, variant, run, result, and
provider-credential endpoints require `Authorization: Bearer ...`. Users see
only their own projects and all nested resources inherit that ownership.

Login failures are rate-limited by a hash of the client/account identifier.
Local development defaults to an in-memory limiter. Full-stack Compose uses
Redis so limits are shared and survive API process restarts. A successful login
clears its failure bucket; blocked requests return `429` and `Retry-After`.

Each refresh token is random and opaque. PostgreSQL stores only its SHA-256
hash. Rotation revokes the old row and links it to its replacement. Replaying a
rotated token revokes the entire session family. Logout revokes refresh access;
an already issued access token remains valid only until its short expiration.

Verification and recovery tokens are random, single-use, and expire after 24
hours and 30 minutes respectively by default. Only SHA-256 hashes are stored in
PostgreSQL. Request endpoints always return the same `202 Accepted` response for
known and unknown addresses, and they share the authentication rate limiter.
Account-action links keep the token in the URL fragment so it is not sent to the
frontend server or included in ordinary HTTP referrers.

For local development, `EMAIL_BACKEND=console` writes the link to API logs. A
public deployment must use `EMAIL_BACKEND=smtp` and configure `SMTP_HOST`,
`SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_STARTTLS`,
`EMAIL_FROM_ADDRESS`, and the public HTTPS `FRONTEND_PUBLIC_URL`. The frontend
contains verification, resend, forgot-password, and new-password flows.

## CRUD API

All data-management endpoints use the `/api/v1` prefix. Collection endpoints
support `offset` and `limit` query parameters; `limit` is capped at 100.

| Resource | Create and list | Read, update, and delete |
| --- | --- | --- |
| Projects | `POST/GET /api/v1/projects` | `/api/v1/projects/{project_id}` |
| Datasets | `POST/GET /api/v1/projects/{project_id}/datasets` | `/api/v1/datasets/{dataset_id}` |
| Dataset items | `POST/GET /api/v1/datasets/{dataset_id}/items` | `/api/v1/dataset-items/{item_id}` |
| Variants | `POST/GET /api/v1/projects/{project_id}/variants` | `/api/v1/variants/{variant_id}` |
| Provider credentials | `POST/GET /api/v1/provider-credentials` | `/api/v1/provider-credentials/{credential_id}` |

The authenticated provider catalog is available at
`GET /api/v1/providers/catalog`. Test a saved credential explicitly with
`POST /api/v1/provider-credentials/{credential_id}/test`; its body contains the
provider-specific LiteLLM model ID. Testing makes one minimal real API request.
Discover the models visible to a saved key with
`GET /api/v1/provider-credentials/{credential_id}/models`; add
`?refresh=true` to bypass the bounded in-memory cache. This ownership-protected
response contains model IDs and discovery metadata, never the API key.
Deleting a credential attached to a model variant returns `409`.

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
2. Open **AI Providers** and add or test your personal provider credentials.
3. Open **Models**, add the model variants you want to compare, enter their
   LiteLLM model IDs, and attach the matching saved credentials. Selecting a
   credential loads its current provider model catalog; manual entry remains
   available for new, private, or custom models.
4. Open **Evaluation runs**, choose a dataset, select one or more models, set
   the number of parallel workers, and select **Start evaluation**.
5. Keep the run open to see task progress and partial results refresh every
   1.5 seconds. You may cancel a pending or running evaluation.
6. Inspect the model leaderboard and expand individual prompts to compare the
   expected answer with each model output.

The frontend never receives plaintext provider keys after submission. The
browser calls the authenticated backend, credentials are decrypted only while
the worker prepares a provider request, and Celery messages contain only the
run ID. Keys are excluded from model serialization, logs, traces, and persisted
results. A provider failure is shown on its individual task row and does not
hide successful model results from the same run.

### Live Run Analytics

As soon as the first result is persisted, the selected run displays five
model-comparison charts: average quality, average latency, total token usage,
estimated cost, and provider errors. Charts update with the existing 1.5-second
run polling cycle, so no additional analytics endpoint or browser request is
required. The best current value is highlighted; quality is maximized, while
latency, token usage, cost, and errors are minimized. Models without a saved
result are excluded from the snapshot to avoid presenting zeroes as winners.

### Filtering Individual Results

The individual-results table can be searched by prompt, limited to one model,
or filtered to successful tasks, provider errors, or answers with quality below
67%. Results can be sorted in either direction by quality, latency, or total
tokens while dataset order remains the default. Sorting is stable, missing
metrics stay at the end, and a single action clears every active control.

Filtering and sorting happen in memory over the selected run detail. They do
not trigger provider calls, change persisted results, or add network requests.
Controls reset when another run is selected so that a model from the previous
run cannot produce a misleading empty state.

### Comparing Completed Runs

Projects with at least two completed evaluations can compare an earlier
baseline with a later candidate. The comparison loads both persisted run
details and calculates changes in average quality, average latency, total
tokens, estimated cost, and provider errors. Each delta is marked as improved,
regressed, or unchanged according to the metric direction.

A model-by-model table matches variants by name and shows before/after values
alongside each delta. Models that exist in only one run are marked as new or
removed. The UI warns when the selected runs use different datasets or model
sets because their overall totals are not directly comparable. Comparison is
read-only and does not create provider calls or database records.

### Exporting Runs and Comparisons

Every loaded run can be downloaded as JSON or CSV from its detail header. The
JSON file preserves the complete persisted run, including its aggregate summary
and individual results. The CSV file contains one row per model response with
the prompt, reference answer, output, metrics, latency, token usage, estimated
cost, retries, and error details.

An open run-to-run comparison has its own JSON and CSV actions. Comparison JSON
stores the baseline and candidate summaries, compatibility warnings, overall
deltas, per-model deltas, and improved/regressed/unchanged outcomes. Comparison
CSV uses a long format with one metric per row, which is convenient for Excel,
BI tools, and custom analysis scripts. UTF-8 BOM support keeps non-ASCII prompts
readable in spreadsheet applications, and potentially executable spreadsheet
formula prefixes are neutralized.

All export files are assembled from already loaded browser data. Exporting does
not call GroqCloud, create a database record, or add a backend endpoint.

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

## Continuous Integration

The `.github/workflows/ci.yml` workflow runs on pushes to `main`, pull requests,
manual dispatches, and as the reusable quality gate for releases. It grants the generated `GITHUB_TOKEN` only
`contents: read` and never loads real provider, SMTP, database, or deployment
secrets.

The quality gate contains five jobs:

1. **Backend tests and migrations** — installs Python 3.12 dependencies from
   `pyproject.toml`, compiles the packages, runs the complete network-free
   pytest suite, and renders the full Alembic SQL chain.
2. **Frontend lint, build, and tests** — installs the exact npm lockfile on
   Node.js 22, runs ESLint, builds the production Vinext bundle, and executes
   server-render/security tests.
3. **Configuration validation** — checks the provisioning/deployment shell
   scripts and parses the local full-stack, hardened production, and
   backup-drill configurations with non-secret CI placeholder values.
4. **Backup/restore drill** — migrates a fresh PostgreSQL source, creates an
   encrypted restic snapshot, restores it into an isolated target, and verifies
   the schema plus public tables.
5. **Container builds** — runs only after the first four jobs pass and builds
   all three non-root production images without pushing them to a registry.

Concurrent runs for the same branch are cancelled when a newer commit arrives.
Dependency caches contain package-manager downloads, not installed virtual
environments or `node_modules`. Dependabot checks GitHub Actions, pip, npm, and
all three Dockerfiles every week.

The workflow intentionally uses `pull_request`, not `pull_request_target`, and
has no publish/deploy credentials. The separate release workflow receives only
`contents: read` and `packages: write`, and only after the complete reusable CI
workflow succeeds.

## Production Releases and HTTPS Deployment

Pushing a semantic version tag such as `v0.34.0` starts
`.github/workflows/release.yml`. It reruns the complete CI quality gate, then
builds Linux AMD64 and ARM64 API/frontend/backup images and publishes exact-version,
minor-version, and stable `latest` tags to GitHub Container Registry. Published
images include OCI source/revision labels, build provenance, and an SBOM.

After that release succeeds, the separate **Deploy production** workflow can
deploy the exact tag. It runs only through manual dispatch, requires the literal
confirmation `deploy-production`, serializes production changes, and enters the
GitHub `production` Environment before any deployment secret is available.
Configure a required reviewer and restrict deployment branches/tags in that
Environment. The workflow verifies all three GHCR manifests, checks out the
matching tag, pins the server host key, and sends only the release bundle plus a
protected environment file to the server.

`compose.production.yaml` is intentionally separate from the local development
stack. It pulls immutable release images, forces secure refresh cookies, uses
Redis-backed authentication rate limiting, requires database/Redis/application
secrets, and exposes only Caddy on ports `80` and `443`. PostgreSQL and Redis
share an internal Docker network; the Celery worker receives outbound network
access for model-provider calls without publishing a host port. Caddy obtains
and renews the domain certificate, redirects HTTP to HTTPS, adds baseline
security headers, and routes `/api/*` and `/health` to FastAPI. `/ready`,
`/metrics`, API documentation, databases, and worker metrics stay private.

The cloud-neutral bootstrap in `infra/provision-ubuntu.sh` prepares a fresh
supported Ubuntu host with Docker's official packages, a dedicated deployment
account, fail2ban, and unattended security updates. The remote deployment script
validates a candidate environment before activating it, takes an encrypted
database backup on upgrades, locks concurrent deploys, waits for migrations and
all service health checks, and finally verifies public HTTPS. It preserves the
previous environment file for an operator-led rollback; database migrations are
forward-only and are never rolled back automatically.

Copy `.env.production.example`, replace every placeholder, point the domain DNS
record at the server, and follow the bootstrap, GitHub Environment, release,
deployment, and recovery instructions in [DEPLOYMENT.md](DEPLOYMENT.md). The
production environment file is explicitly ignored by Git; only its placeholder
template is tracked.

### Encrypted Backups and Restore Drills

The production stack includes a dedicated non-root backup image combining the
PostgreSQL 17 client with restic 0.19.1. On startup and every 24 hours by
default, it creates a custom-format `pg_dump`, writes the dump into the
encrypted restic repository, applies daily/weekly/monthly retention, and
atomically records the last successful backup time. Failed attempts retry after
five minutes without stopping the API, worker, or frontend.

Configure an off-site repository in `.env.production`:

```dotenv
EVALFLOW_BACKUP_IMAGE=ghcr.io/foreg0n/llm-evaluation-platform-backup:0.34.0
RESTIC_REPOSITORY=s3:https://s3.example.com/evalflow-production/postgres
RESTIC_PASSWORD=replace-with-an-independent-encryption-password
AWS_ACCESS_KEY_ID=replace-with-object-storage-access-key
AWS_SECRET_ACCESS_KEY=replace-with-object-storage-secret-key
AWS_DEFAULT_REGION=auto
BACKUP_KEEP_DAILY=7
BACKUP_KEEP_WEEKLY=5
BACKUP_KEEP_MONTHLY=12
```

`RESTIC_PASSWORD` encrypts the repository and must be stored separately from
the bucket. Back up `CREDENTIAL_ENCRYPTION_KEY` in a secret manager as well:
the database contains encrypted BYOK values, but the database backup does not
contain the Fernet key required to decrypt them.

Check freshness, trigger an on-demand backup, and list snapshots:

```bash
docker compose --env-file .env.production -f compose.production.yaml exec backup health
docker compose --env-file .env.production -f compose.production.yaml run --rm backup backup
docker compose --env-file .env.production -f compose.production.yaml run --rm backup restic snapshots --tag evalflow-postgres
```

The restore profile never writes into the live database. It restores the latest
snapshot into a temporary PostgreSQL container, runs `pg_restore
--exit-on-error`, reads the Alembic version, and enforces a minimum public-table
count:

```bash
docker compose --env-file .env.production -f compose.production.yaml \
  --profile restore up --abort-on-container-exit \
  --exit-code-from restore-drill restore-drill
docker compose --env-file .env.production -f compose.production.yaml \
  --profile restore rm -f restore-drill restore-postgres
```

CI performs the same full backup-and-restore sequence against fresh source and
target databases using `compose.backup-drill.yaml`. This verifies that a backup
is actually restorable rather than merely checking that an archive file exists.
See [DEPLOYMENT.md](DEPLOYMENT.md) for retention, recovery, and cleanup details.

## Running Tests

```bash
pytest
```

Tests inject mocked completion functions into `LiteLLMProvider` and the run API.
Backend integration tests use a temporary SQLite database and cover registration,
email verification, password recovery, one-time/expired account tokens, login,
refresh rotation/replay, logout, auth rate limiting, encrypted provider
credentials, protected routes, and cross-user isolation. They do not read real
API keys, connect to SMTP, Redis, or provider APIs, or modify PostgreSQL.
Model-catalog tests inject fake discovery loaders, so CI never spends provider
credits or depends on external model availability.

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
provider completions into the project's `GenerationResponse`, including token
and cost data. The runner creates one task per dataset-item/model pair and uses an
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
│   ├── credential_security.py
│   ├── error_monitoring.py
│   ├── metrics.py
│   ├── observability.py
│   ├── provider_catalog.py
│   ├── security.py
│   ├── tracing.py
│   └── main.py
├── Dockerfile
├── deploy/
│   ├── backup/
│   │   ├── scripts/
│   │   └── Dockerfile
│   ├── scripts/
│   │   └── deploy-production.sh
│   └── Caddyfile
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
│   │   ├── page.tsx
│   │   └── provider-workspace.tsx
│   ├── public/
│   ├── tests/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── .env.example
│   └── package.json
├── infra/
│   ├── provision-ubuntu.sh
│   └── README.md
├── observability/
│   ├── grafana/
│   │   ├── dashboards/
│   │   └── provisioning/
│   ├── prometheus/
│       ├── alerts.yml
│       └── prometheus.yml
│   └── tempo/
│       └── tempo.yml
├── artifacts/
├── tests/
├── .env.example
├── .env.production.example
├── .dockerignore
├── compose.backup-drill.yaml
├── compose.production.yaml
├── compose.yaml
├── compose.observability.yaml
├── compose.redis.yaml
├── .gitignore
├── pyproject.toml
└── README.md
```

## Current Scope

The asynchronous CLI, authenticated CRUD API, persisted API-managed runs, and
the core frontend experiment workflow are usable today. The backend includes
configuration, FastAPI, PostgreSQL migrations, validation, per-user ownership, selectable
in-process or Redis/Celery execution, progress, cancellation, resumable
delivery, summaries, and result history. The frontend includes authentication,
real overview statistics, projects, recent runs, project creation, project
workspaces, full dataset/test-case management, atomic file import, model-variant
management, evaluation launch, live progress and cancellation, detailed result
comparison, and live charts for the five primary performance dimensions.
Individual task results also support prompt search, model and status filters,
weak-answer detection, and metric sorting. Two completed runs can be compared
through overall and model-level quality, latency, token, cost, and error deltas.
Selected runs and comparisons can be exported locally as JSON or CSV without
new provider or backend requests. Backend requests, evaluation executions, and
Celery tasks emit structured lifecycle logs with correlation identifiers.
Prometheus endpoints expose bounded API/run/worker metrics, while `/ready`
separately reports PostgreSQL and configured queue readiness. A reproducible
Prometheus/Grafana Compose stack now scrapes those endpoints, provisions a
source-controlled overview dashboard, and evaluates seven operational alerts.
Optional OpenTelemetry instrumentation connects FastAPI request spans to Celery
task spans, enriches structured logs with trace identifiers, and exports traces
to the local Tempo datasource in Grafana. Optional Sentry integration captures
unhandled API, worker, and persisted-run failures with correlation tags and
strict event scrubbing, while leaving OpenTelemetry as the only tracing layer.
The complete application also has production-oriented, non-root Docker images
and a dependency-ordered local Compose topology with persistent PostgreSQL/Redis,
automatic migrations, localhost-only published ports, and health-gated startup.
The separate production topology adds Caddy-managed HTTPS, same-origin API
routing, security headers, private service networks, authenticated Redis, and
required secret interpolation. Semantic Git tags run the complete reusable CI
gate before multi-architecture API, frontend, and backup images with provenance and an
SBOM are published to GHCR. A scheduled backup service now produces encrypted
off-site PostgreSQL snapshots with bounded retention and freshness health
checks. The CI and production restore profiles prove the latest snapshot can be
loaded into an isolated database with a valid Alembic version and expected
schema size. A cloud-neutral Ubuntu bootstrap and protected GitHub deployment
workflow now automate a first single-server deployment without embedding cloud
credentials. Deployments are manual, serialized, bound to an exact release tag,
protected by pinned SSH host identity and Environment approval, and gated by a
pre-deploy backup, successful migration, internal service health, and public
HTTPS health.
Users can manage encrypted BYOK credentials for multiple providers from the UI,
test them explicitly, and bind different credentials to individual model
variants. The worker resolves those credentials at execution time without
placing plaintext secrets in Celery messages or evaluation records.
The model editor now discovers the current catalog available to the selected
credential through provider model-list endpoints, caches normalized results,
supports an explicit refresh, and degrades to LiteLLM suggestions or manual
entry without exposing the key to the browser.
Authentication now uses memory-only access tokens plus rotating HttpOnly
refresh sessions, supports current/all-session revocation, detects refresh-token
replay, and rate-limits credential attempts through Redis in Docker Compose.
New accounts require email verification, and the password-recovery flow uses
short-lived one-time tokens, generic request responses, and all-session
revocation after a successful reset.

Large-run pagination, durable email/notification delivery, automated
error/alert notification delivery, cloud-specific
infrastructure-as-code, object-storage immutability policy, a managed secret
store, and the first public cloud deployment remain future stages.
