# Contributing to Evalflow

Evalflow is a personal portfolio project, but focused bug reports and pull
requests are welcome.

## Development Setup

Use Python 3.12 or newer and Node.js 22.13 or newer. Install the backend and
frontend dependencies with:

```bash
python -m pip install -e ".[dev]"
cd frontend
npm ci
```

Copy `.env.example` to `.env`, generate fresh local secrets as described in the
README, and start PostgreSQL and Redis. Never commit `.env` files or real API
keys.

## Before Opening a Pull Request

Run the same checks enforced by CI:

```bash
python scripts/release_audit.py
python -m ruff check backend evals tests scripts
python -m pytest
python -m compileall -q backend evals
alembic upgrade head --sql > alembic.sql
cd frontend
npm run lint
npm run audit:production
npm test
```

Keep changes scoped, add network-free tests for backend behavior, and update
the README when user-facing behavior changes. Provider tests must use mocks;
the test suite must never contact a real model API.

## Pull Requests

Describe the problem, the solution, and how you verified it. Include migration
notes for schema changes and screenshots for visible frontend changes.
