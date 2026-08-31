from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_deployment_is_manual_serialized_and_environment_protected() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "deploy.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = load_yaml(workflow_path)
    triggers = workflow.get("on", workflow.get(True))
    jobs = workflow["jobs"]

    assert set(triggers) == {"workflow_dispatch"}
    assert workflow["permissions"] == {
        "contents": "read",
        "packages": "read",
    }
    assert workflow["concurrency"] == {
        "group": "production-deployment",
        "cancel-in-progress": False,
    }
    assert jobs["deploy"]["needs"] == "validate"
    assert jobs["deploy"]["environment"]["name"] == "production"
    assert jobs["deploy"]["environment"]["url"].startswith("https://")
    assert "pull_request" not in triggers
    assert "pull_request_target" not in workflow_text


def test_deployment_requires_exact_tag_images_and_explicit_confirmation() -> None:
    workflow_text = (
        ROOT / ".github" / "workflows" / "deploy.yml"
    ).read_text(encoding="utf-8")

    assert '"deploy-production"' in workflow_text
    assert "ref: v${{ inputs.version }}" in workflow_text
    assert "for component in api frontend backup" in workflow_text
    assert "docker manifest inspect" in workflow_text
    assert "actions/checkout@v7" in workflow_text
    assert "docker/login-action@v4" in workflow_text


def test_deployment_pins_ssh_identity_and_keeps_secrets_in_environment() -> None:
    workflow_text = (
        ROOT / ".github" / "workflows" / "deploy.yml"
    ).read_text(encoding="utf-8")

    assert "secrets.DEPLOY_SSH_PRIVATE_KEY" in workflow_text
    assert "secrets.DEPLOY_SSH_KNOWN_HOSTS" in workflow_text
    assert "secrets.PRODUCTION_ENV_FILE" in workflow_text
    assert "StrictHostKeyChecking=yes" in workflow_text
    assert "UserKnownHostsFile=" in workflow_text
    assert "ssh-keyscan" not in workflow_text
    assert "rm -rf \"$RUNNER_TEMP/evalflow-ssh\"" in workflow_text


def test_remote_deploy_locks_validates_backs_up_and_checks_health() -> None:
    script = (
        ROOT / "deploy" / "scripts" / "deploy-production.sh"
    ).read_text(encoding="utf-8")

    assert "flock -n" in script
    assert ".env.production.candidate" in script
    assert 'config --quiet' in script
    assert 'exec -T backup health' in script
    assert 'run --rm backup backup' in script
    assert 'up -d --remove-orphans' in script
    assert "migration_failed" in script
    assert "wait_for_healthy_service" in script
    assert '"https://$app_domain/health"' in script
    assert "down --volumes" not in script
    assert "down -v" not in script


def test_ubuntu_bootstrap_is_bounded_idempotent_and_key_only() -> None:
    script = (ROOT / "infra" / "provision-ubuntu.sh").read_text(
        encoding="utf-8"
    )

    assert "22.04|24.04|26.04" in script
    assert "https://download.docker.com/linux/ubuntu" in script
    assert "docker-ce docker-ce-cli containerd.io" in script
    assert "docker-buildx-plugin docker-compose-plugin" in script
    assert "EVALFLOW_SSH_PUBLIC_KEY" in script
    assert "authorized_keys" in script
    assert "passwd --lock" in script
    assert "usermod --append --groups docker" in script
    assert "systemctl enable --now fail2ban unattended-upgrades" in script
    assert "apt-get remove" not in script
