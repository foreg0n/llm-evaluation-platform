from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
BACKUP_ROOT = ROOT / "deploy" / "backup"


def read_script(name: str) -> str:
    return (BACKUP_ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_backup_image_combines_pinned_restic_and_postgres_tools() -> None:
    dockerfile = (BACKUP_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM restic/restic:0.19.1 AS restic" in dockerfile
    assert "FROM postgres:17-alpine" in dockerfile
    assert "COPY --from=restic /usr/bin/restic" in dockerfile
    assert "USER postgres" in dockerfile
    assert 'ENTRYPOINT ["/opt/evalflow-backup/entrypoint.sh"]' in dockerfile


def test_backup_creates_custom_dump_encrypts_and_applies_retention() -> None:
    script = read_script("backup-once.sh")

    assert "pg_isready" in script
    assert "pg_dump" in script
    assert "--format=custom" in script
    assert 'restic backup "$dump_path"' in script
    assert "restic forget" in script
    assert "--keep-daily" in script
    assert "--keep-weekly" in script
    assert "--keep-monthly" in script
    assert 'BACKUP_PRUNE="${BACKUP_PRUNE:-true}"' in script
    assert 'mv "$state_tmp" "$BACKUP_STATE_DIR/last-success"' in script


def test_restore_drill_checks_repository_schema_and_table_count() -> None:
    script = read_script("restore-drill.sh")

    assert "restic check" in script
    assert "restic restore latest" in script
    assert "pg_restore" in script
    assert "--exit-on-error" in script
    assert "SELECT version_num FROM alembic_version" in script
    assert "information_schema.tables" in script
    assert "RESTORE_MIN_PUBLIC_TABLES" in script
    assert '"status":"ok"' in script


def test_backup_health_is_based_on_last_success_age() -> None:
    healthcheck = read_script("healthcheck.sh")
    loop = read_script("backup-loop.sh")

    assert "last-success" in healthcheck
    assert "BACKUP_MAX_AGE_SECONDS" in healthcheck
    assert "backup_health_ok" in healthcheck
    assert "BACKUP_INTERVAL_SECONDS" in loop
    assert "BACKUP_RETRY_SECONDS" in loop
    assert "backup_failed" in loop


def test_drill_compose_restores_only_after_migration_and_backup() -> None:
    compose = yaml.safe_load(
        (ROOT / "compose.backup-drill.yaml").read_text(encoding="utf-8")
    )
    services = compose["services"]

    assert set(services) == {
        "source-postgres",
        "migrate",
        "backup",
        "restore-postgres",
        "restore-drill",
    }
    assert services["backup"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["restore-drill"]["depends_on"]["backup"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["restore-postgres"]["tmpfs"] == [
        "/var/lib/postgresql/data"
    ]
    assert "ports" not in services["source-postgres"]
    assert "ports" not in services["restore-postgres"]
