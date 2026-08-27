#!/usr/bin/env bash

set -Eeuo pipefail

log() {
    printf '%s level=%s event=%s %s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "${3:-}"
}

VERSION="${1:-}"
REPOSITORY_SLUG="${2:-}"
APP_DIR="${EVALFLOW_APP_DIR:-/opt/evalflow}"
DEPLOY_TIMEOUT_SECONDS="${DEPLOY_TIMEOUT_SECONDS:-600}"

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
    log error invalid_version "value=$VERSION"
    exit 1
fi
if [[ ! "$REPOSITORY_SLUG" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
    log error invalid_repository "value=$REPOSITORY_SLUG"
    exit 1
fi
if [[ ! "$DEPLOY_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] || (( DEPLOY_TIMEOUT_SECONDS < 60 )); then
    log error invalid_timeout "value=$DEPLOY_TIMEOUT_SECONDS"
    exit 1
fi

cd "$APP_DIR"
exec 9>"$APP_DIR/.deploy.lock"
if ! flock -n 9; then
    log error deployment_locked "Another deployment is running."
    exit 1
fi

compose_file="$APP_DIR/compose.production.yaml"
incoming_env="$APP_DIR/.env.production.incoming"
candidate_env="$APP_DIR/.env.production.candidate"
active_env="$APP_DIR/.env.production"
previous_env="$APP_DIR/.env.production.previous"

if [[ ! -f "$compose_file" || ! -f "$APP_DIR/deploy/Caddyfile" ]]; then
    log error deployment_bundle_incomplete
    exit 1
fi
if [[ ! -f "$incoming_env" || -L "$incoming_env" ]]; then
    log error production_environment_missing
    exit 1
fi

cleanup() {
    rm -f "$candidate_env" "$incoming_env"
}
trap cleanup EXIT

install -m 0600 "$incoming_env" "$candidate_env"
sed -i 's/\r$//' "$candidate_env"
rm -f "$incoming_env"

set_env_value() {
    local key="$1"
    local value="$2"
    local source_file="$3"
    local temporary_file
    temporary_file="$(mktemp "$APP_DIR/.env.production.update.XXXXXX")"
    awk -v key="$key" -v value="$value" '
        BEGIN { updated = 0 }
        index($0, key "=") == 1 { print key "=" value; updated = 1; next }
        { print }
        END { if (!updated) print key "=" value }
    ' "$source_file" > "$temporary_file"
    chmod 0600 "$temporary_file"
    mv "$temporary_file" "$source_file"
}

repository_lower="${REPOSITORY_SLUG,,}"
set_env_value EVALFLOW_API_IMAGE \
    "ghcr.io/$repository_lower-api:$VERSION" "$candidate_env"
set_env_value EVALFLOW_FRONTEND_IMAGE \
    "ghcr.io/$repository_lower-frontend:$VERSION" "$candidate_env"
set_env_value EVALFLOW_BACKUP_IMAGE \
    "ghcr.io/$repository_lower-backup:$VERSION" "$candidate_env"

if grep -Eq '=(replace-with-|change-me|your-secret)' "$candidate_env"; then
    log error production_placeholders_detected
    exit 1
fi

candidate_compose=(docker compose --env-file "$candidate_env" -f "$compose_file")
"${candidate_compose[@]}" config --quiet

if [[ -f "$active_env" ]]; then
    current_compose=(docker compose --env-file "$active_env" -f "$compose_file")
    backup_container="$("${current_compose[@]}" ps -q backup 2>/dev/null || true)"
    if [[ -n "$backup_container" ]]; then
        log info predeploy_backup_started
        "${current_compose[@]}" exec -T backup health
        "${current_compose[@]}" run --rm backup backup
        log info predeploy_backup_completed
    fi
    install -m 0600 "$active_env" "$previous_env"
fi

log info image_pull_started "version=$VERSION"
"${candidate_compose[@]}" pull
mv "$candidate_env" "$active_env"
chmod 0600 "$active_env"
trap - EXIT

compose=(docker compose --env-file "$active_env" -f "$compose_file")
log info deployment_started "version=$VERSION"
"${compose[@]}" up -d --remove-orphans

wait_for_healthy_service() {
    local service="$1"
    local deadline=$(( $(date +%s) + DEPLOY_TIMEOUT_SECONDS ))
    local container_id status
    while (( $(date +%s) < deadline )); do
        container_id="$("${compose[@]}" ps -q "$service")"
        if [[ -n "$container_id" ]]; then
            status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
            if [[ "$status" == "healthy" || "$status" == "running" ]]; then
                log info service_ready "service=$service status=$status"
                return 0
            fi
            if [[ "$status" == "unhealthy" || "$status" == "exited" || "$status" == "dead" ]]; then
                log error service_failed "service=$service status=$status"
                return 1
            fi
        fi
        sleep 5
    done
    log error service_timeout "service=$service"
    return 1
}

migrate_container="$("${compose[@]}" ps -a -q migrate)"
if [[ -z "$migrate_container" ]]; then
    log error migration_container_missing
    exit 1
fi
migrate_status="$(docker inspect --format '{{.State.Status}}' "$migrate_container")"
migrate_exit="$(docker inspect --format '{{.State.ExitCode}}' "$migrate_container")"
if [[ "$migrate_status" != "exited" || "$migrate_exit" != "0" ]]; then
    log error migration_failed "status=$migrate_status exit_code=$migrate_exit"
    "${compose[@]}" logs --tail=200 migrate
    exit 1
fi

for service in postgres redis api worker backup frontend caddy; do
    if ! wait_for_healthy_service "$service"; then
        "${compose[@]}" logs --tail=200 "$service"
        exit 1
    fi
done

app_domain="$(awk -F= '$1 == "APP_DOMAIN" { sub(/^[^=]*=/, ""); print; exit }' "$active_env")"
if [[ ! "$app_domain" =~ ^[A-Za-z0-9.-]+$ ]]; then
    log error invalid_app_domain
    exit 1
fi
curl --fail --silent --show-error \
    --retry 12 --retry-delay 5 --retry-all-errors --max-time 15 \
    "https://$app_domain/health" >/dev/null

printf '%s deployed_at=%s\n' "$VERSION" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$APP_DIR/.deployed-version"
"${compose[@]}" ps -a
log info deployment_completed "version=$VERSION url=https://$app_domain"
