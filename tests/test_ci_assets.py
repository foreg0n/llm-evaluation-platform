from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_ci_has_read_only_permissions_and_safe_triggers() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "ci.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = load_yaml(workflow_path)
    triggers = workflow.get("on", workflow.get(True))

    assert set(triggers) == {
        "workflow_call",
        "push",
        "pull_request",
        "workflow_dispatch",
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert "pull_request_target" not in workflow_text
    assert "secrets." not in workflow_text


def test_ci_covers_backend_frontend_configuration_and_images() -> None:
    workflow = load_yaml(ROOT / ".github" / "workflows" / "ci.yml")
    jobs = workflow["jobs"]

    assert set(jobs) == {
        "backend",
        "frontend",
        "configuration",
        "backup-restore",
        "containers",
    }
    assert jobs["containers"]["needs"] == [
        "backend",
        "frontend",
        "configuration",
        "backup-restore",
    ]
    all_runs = "\n".join(
        str(step.get("run", ""))
        for job in jobs.values()
        for step in job["steps"]
    )
    assert "python -m pytest" in all_runs
    assert "alembic upgrade head --sql" in all_runs
    assert "npm ci" in all_runs
    assert "npm run lint" in all_runs
    assert "npm test" in all_runs
    assert "docker compose config --quiet" in all_runs
    assert "compose.production.yaml config --quiet" in all_runs
    assert "compose.backup-drill.yaml config --quiet" in all_runs
    assert "caddy validate --config /etc/caddy/Caddyfile" in all_runs
    assert "compose.backup-drill.yaml" in all_runs
    assert "run --rm --no-deps backup" in all_runs
    assert "run --rm --no-deps restore-drill" in all_runs
    assert "docker build --tag evalflow-api:ci ." in all_runs
    assert "--tag evalflow-frontend:ci" in all_runs
    assert "docker build --tag evalflow-backup:ci" in all_runs


def test_ci_uses_current_action_majors_and_locked_dependencies() -> None:
    workflow_text = (
        ROOT / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    assert "actions/checkout@v7" in workflow_text
    assert "actions/setup-python@v7" in workflow_text
    assert "actions/setup-node@v6" in workflow_text
    assert "cache-dependency-path: pyproject.toml" in workflow_text
    assert "cache-dependency-path: frontend/package-lock.json" in workflow_text


def test_dependabot_tracks_every_dependency_ecosystem() -> None:
    config = load_yaml(ROOT / ".github" / "dependabot.yml")
    ecosystems = [entry["package-ecosystem"] for entry in config["updates"]]

    assert ecosystems.count("docker") == 3
    assert set(ecosystems) == {"github-actions", "pip", "npm", "docker"}
    assert all(
        entry["schedule"]["interval"] == "weekly"
        for entry in config["updates"]
    )
