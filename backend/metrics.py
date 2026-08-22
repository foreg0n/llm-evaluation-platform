from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


METRICS_REGISTRY = CollectorRegistry()

HTTP_REQUESTS = Counter(
    "evalflow_http_requests",
    "Completed HTTP requests.",
    ("method", "route", "status_code"),
    registry=METRICS_REGISTRY,
)
HTTP_REQUEST_DURATION = Histogram(
    "evalflow_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    registry=METRICS_REGISTRY,
)
EVALUATION_RUNS = Counter(
    "evalflow_evaluation_runs",
    "Evaluation runs reaching a terminal outcome.",
    ("outcome",),
    registry=METRICS_REGISTRY,
)
EVALUATION_RUNS_IN_PROGRESS = Gauge(
    "evalflow_evaluation_runs_in_progress",
    "Evaluation runs currently executing in this process.",
    registry=METRICS_REGISTRY,
    multiprocess_mode="livesum",
)
EVALUATION_RUN_DURATION = Histogram(
    "evalflow_evaluation_run_duration_seconds",
    "Evaluation run execution duration in seconds.",
    ("outcome",),
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800, 3600),
    registry=METRICS_REGISTRY,
)
CELERY_TASKS = Counter(
    "evalflow_celery_tasks",
    "Celery evaluation tasks reaching a terminal outcome.",
    ("outcome",),
    registry=METRICS_REGISTRY,
)
CELERY_TASKS_IN_PROGRESS = Gauge(
    "evalflow_celery_tasks_in_progress",
    "Celery evaluation tasks currently executing in this worker process.",
    registry=METRICS_REGISTRY,
    multiprocess_mode="livesum",
)
CELERY_TASK_DURATION = Histogram(
    "evalflow_celery_task_duration_seconds",
    "Celery evaluation task duration in seconds.",
    ("outcome",),
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800, 3600),
    registry=METRICS_REGISTRY,
)
READINESS_CHECKS = Counter(
    "evalflow_readiness_checks",
    "Readiness component checks by result.",
    ("component", "status"),
    registry=METRICS_REGISTRY,
)


def observe_http_request(
    *,
    method: str,
    route: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    HTTP_REQUESTS.labels(
        method=method,
        route=route,
        status_code=str(status_code),
    ).inc()
    HTTP_REQUEST_DURATION.labels(method=method, route=route).observe(
        duration_seconds
    )


def observe_evaluation_run(*, outcome: str, duration_seconds: float) -> None:
    EVALUATION_RUNS.labels(outcome=outcome).inc()
    EVALUATION_RUN_DURATION.labels(outcome=outcome).observe(duration_seconds)


def observe_celery_task(*, outcome: str, duration_seconds: float) -> None:
    CELERY_TASKS.labels(outcome=outcome).inc()
    CELERY_TASK_DURATION.labels(outcome=outcome).observe(duration_seconds)
