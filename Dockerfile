FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv

RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /build
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY evals ./evals
RUN python -m pip install --upgrade pip && python -m pip install .


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN addgroup --system --gid 10001 evalflow \
    && adduser --system --uid 10001 --ingroup evalflow --home /app evalflow

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=evalflow:evalflow alembic ./alembic
COPY --chown=evalflow:evalflow alembic.ini pyproject.toml README.md ./
COPY --chown=evalflow:evalflow backend ./backend
COPY --chown=evalflow:evalflow evals ./evals
RUN mkdir -p /app/artifacts && chown evalflow:evalflow /app/artifacts

USER evalflow
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
