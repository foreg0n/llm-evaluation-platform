from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_full_stack_compose_declares_required_services_and_storage() -> None:
    compose = load_yaml(ROOT / "compose.yaml")
    services = compose["services"]

    assert compose["name"] == "evalflow"
    assert set(services) == {
        "postgres",
        "redis",
        "migrate",
        "api",
        "worker",
        "frontend",
    }
    assert services["postgres"]["image"] == "postgres:17-alpine"
    assert services["redis"]["image"] == "redis:8.2-alpine"
    assert set(compose["volumes"]) == {"postgres_data", "redis_data"}
    assert services["postgres"]["ports"][0].startswith("127.0.0.1:")
    assert services["redis"]["ports"][0].startswith("127.0.0.1:")
    assert "healthcheck" in services["postgres"]
    assert "healthcheck" in services["redis"]


def test_compose_runs_migrations_before_healthy_api_and_worker() -> None:
    services = load_yaml(ROOT / "compose.yaml")["services"]

    assert services["migrate"]["command"] == ["alembic", "upgrade", "head"]
    assert services["migrate"]["depends_on"]["postgres"]["condition"] == (
        "service_healthy"
    )
    assert services["api"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["worker"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["api"]["depends_on"]["redis"]["condition"] == (
        "service_healthy"
    )
    assert services["worker"]["depends_on"]["redis"]["condition"] == (
        "service_healthy"
    )
    assert services["api"]["healthcheck"]["test"][0:2] == ["CMD", "python"]
    assert "--reload" not in services["api"]["command"]
    assert "--pool=solo" in services["worker"]["command"]
    assert services["worker"]["healthcheck"]["test"][0:2] == [
        "CMD",
        "python",
    ]


def test_compose_keeps_secrets_external_and_binds_public_ports_locally() -> None:
    compose_text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    services = load_yaml(ROOT / "compose.yaml")["services"]
    backend_environment = load_yaml(ROOT / "compose.yaml")[
        "x-backend-environment"
    ]

    assert "Set POSTGRES_PASSWORD in .env" in compose_text
    assert "Set AUTH_SECRET_KEY in .env" in compose_text
    assert backend_environment["GROQ_API_KEY"] == "${GROQ_API_KEY:-}"
    assert backend_environment["SENTRY_DSN"] == "${SENTRY_DSN:-}"
    assert "@postgres:5432/" in backend_environment["DATABASE_URL"]
    assert "redis://redis:6379/0" == backend_environment["CELERY_BROKER_URL"]
    assert backend_environment["CELERY_METRICS_ENABLED"] == "true"
    assert services["api"]["ports"][0].startswith("127.0.0.1:")
    assert services["worker"]["ports"][0].startswith("127.0.0.1:")
    assert services["frontend"]["ports"][0].startswith("127.0.0.1:")


def test_frontend_uses_browser_api_build_arg_and_standalone_runtime() -> None:
    compose = load_yaml(ROOT / "compose.yaml")
    frontend = compose["services"]["frontend"]
    next_config = (ROOT / "frontend" / "next.config.ts").read_text(
        encoding="utf-8"
    )
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert frontend["build"]["args"]["NEXT_PUBLIC_API_URL"] == (
        "${PUBLIC_API_URL:-http://localhost:8000}"
    )
    assert frontend["depends_on"]["api"]["condition"] == "service_healthy"
    assert 'output: "standalone"' in next_config
    assert "/app/dist/standalone" in dockerfile
    production_install = dockerfile.index("RUN npm ci --omit=dev")
    standalone_copy = dockerfile.index("/app/dist/standalone")
    assert production_install < standalone_copy
    assert 'CMD ["node", "server.js"]' in dockerfile
    assert "USER node" in dockerfile


def test_container_build_contexts_exclude_local_secrets_and_dependencies() -> None:
    backend_ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    frontend_ignore = (ROOT / "frontend" / ".dockerignore").read_text(
        encoding="utf-8"
    )
    backend_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert ".env\n" in backend_ignore
    assert ".venv" in backend_ignore
    assert "frontend" in backend_ignore
    assert ".env\n" in frontend_ignore
    assert "node_modules" in frontend_ignore
    assert "USER evalflow" in backend_dockerfile
    assert 'CMD ["python", "-m", "uvicorn"' in backend_dockerfile
    assert "--reload" not in backend_dockerfile
