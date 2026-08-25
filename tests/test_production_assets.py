from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_production_compose_exposes_only_the_https_gateway() -> None:
    compose = load_yaml(ROOT / "compose.production.yaml")
    services = compose["services"]

    assert set(services) == {
        "postgres",
        "redis",
        "migrate",
        "api",
        "worker",
        "frontend",
        "caddy",
    }
    assert services["caddy"]["ports"] == ["80:80", "443:443", "443:443/udp"]
    assert all(
        "ports" not in service
        for name, service in services.items()
        if name != "caddy"
    )
    assert compose["networks"]["backend"]["internal"] is True
    assert set(services["postgres"]["networks"]) == {"backend"}
    assert set(services["redis"]["networks"]) == {"backend"}
    assert set(services["worker"]["networks"]) == {"backend", "egress"}


def test_production_compose_requires_secrets_and_authenticates_redis() -> None:
    compose_text = (ROOT / "compose.production.yaml").read_text(
        encoding="utf-8"
    )
    compose = yaml.safe_load(compose_text)
    environment = compose["services"]["api"]["environment"]
    redis = compose["services"]["redis"]

    assert "${POSTGRES_PASSWORD:?" in compose_text
    assert "${REDIS_PASSWORD:?" in compose_text
    assert "${AUTH_SECRET_KEY:?" in compose_text
    assert "${CREDENTIAL_ENCRYPTION_KEY:?" in compose_text
    assert "--requirepass" in " ".join(redis["command"])
    assert "--no-auth-warning" in " ".join(redis["healthcheck"]["test"])
    assert "REDIS_PASSWORD" in environment["CELERY_BROKER_URL"]
    assert "REDIS_PASSWORD" in environment["CELERY_RESULT_BACKEND"]
    assert environment["REFRESH_COOKIE_SECURE"] == "true"
    assert environment["AUTH_RATE_LIMIT_BACKEND"] == "redis"


def test_caddy_terminates_https_and_keeps_internal_endpoints_private() -> None:
    caddyfile = (ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")

    assert "{$APP_DOMAIN}" in caddyfile
    assert "reverse_proxy api:8000" in caddyfile
    assert "reverse_proxy frontend:3000" in caddyfile
    assert "@api path /api/* /health" in caddyfile
    assert "/metrics" not in caddyfile
    assert "/ready" not in caddyfile
    assert "Strict-Transport-Security" in caddyfile
    assert "X-Content-Type-Options" in caddyfile
    assert "X-Frame-Options" in caddyfile


def test_release_runs_ci_before_publishing_versioned_ghcr_images() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "release.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = load_yaml(workflow_path)
    triggers = workflow.get("on", workflow.get(True))
    jobs = workflow["jobs"]

    assert set(triggers) == {"push"}
    assert triggers["push"]["tags"] == ["v*.*.*"]
    assert workflow["permissions"] == {"contents": "read"}
    assert jobs["quality"]["needs"] == "validate-tag"
    assert jobs["quality"]["uses"] == "./.github/workflows/ci.yml"
    assert jobs["publish"]["needs"] == "quality"
    assert jobs["publish"]["permissions"] == {
        "contents": "read",
        "packages": "write",
    }
    assert "ghcr.io/${{ github.repository }}-" in workflow_text
    assert "type=semver,pattern={{version}}" in workflow_text
    assert "Release tag must look like v0.31.0" in workflow_text
    assert "push: true" in workflow_text
    assert "provenance: mode=max" in workflow_text
    assert "sbom: true" in workflow_text


def test_release_uses_current_action_majors_and_generic_frontend_origin() -> None:
    workflow_text = (
        ROOT / ".github" / "workflows" / "release.yml"
    ).read_text(encoding="utf-8")

    assert "actions/checkout@v7" in workflow_text
    assert "docker/setup-buildx-action@v4" in workflow_text
    assert "docker/login-action@v4" in workflow_text
    assert "docker/metadata-action@v6" in workflow_text
    assert "docker/build-push-action@v7" in workflow_text
    assert "NEXT_PUBLIC_API_URL=" in workflow_text


def test_production_environment_template_contains_placeholders_only() -> None:
    template = (ROOT / ".env.production.example").read_text(encoding="utf-8")

    assert "APP_DOMAIN=evalflow.example.com" in template
    assert "EVALFLOW_API_IMAGE=ghcr.io/foreg0n/" in template
    assert "EVALFLOW_FRONTEND_IMAGE=ghcr.io/foreg0n/" in template
    assert template.count("replace-with-") >= 6
    assert "CREDENTIAL_ENCRYPTION_KEY=" in template
    assert "GROQ_API_KEY=\n" in template
    assert ".env.production" in (ROOT / ".gitignore").read_text(
        encoding="utf-8"
    ).splitlines()
