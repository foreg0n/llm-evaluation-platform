#!/bin/sh

set -eu

. /opt/evalflow-backup/common.sh

require_env PGHOST
require_env PGDATABASE
require_env PGUSER
require_env PGPASSWORD
require_env RESTIC_REPOSITORY
require_env RESTIC_PASSWORD

BACKUP_KEEP_DAILY="${BACKUP_KEEP_DAILY:-7}"
BACKUP_KEEP_WEEKLY="${BACKUP_KEEP_WEEKLY:-5}"
BACKUP_KEEP_MONTHLY="${BACKUP_KEEP_MONTHLY:-12}"
BACKUP_PRUNE="${BACKUP_PRUNE:-true}"
BACKUP_STATE_DIR="${BACKUP_STATE_DIR:-/state}"
RESTIC_HOST="${RESTIC_HOST:-evalflow-production}"
RESTIC_TAG="${RESTIC_TAG:-evalflow-postgres}"

require_positive_integer BACKUP_KEEP_DAILY
require_positive_integer BACKUP_KEEP_WEEKLY
require_positive_integer BACKUP_KEEP_MONTHLY

mkdir -p "$BACKUP_STATE_DIR"
dump_dir="$(mktemp -d /tmp/evalflow-backup-XXXXXX)"
dump_path="$dump_dir/evalflow-postgres-$(date -u +%Y%m%dT%H%M%SZ).dump"
trap 'rm -rf "$dump_dir"' EXIT HUP INT TERM

log info backup_started "database=$PGDATABASE host=$PGHOST"
pg_isready --quiet --host "$PGHOST" --username "$PGUSER" --dbname "$PGDATABASE"
pg_dump \
    --host "$PGHOST" \
    --username "$PGUSER" \
    --dbname "$PGDATABASE" \
    --format=custom \
    --compress=6 \
    --no-owner \
    --no-privileges \
    --file "$dump_path"

initialize_repository
restic backup "$dump_path" \
    --host "$RESTIC_HOST" \
    --tag "$RESTIC_TAG"

set -- restic forget \
    --host "$RESTIC_HOST" \
    --tag "$RESTIC_TAG" \
    --group-by host,tags \
    --keep-daily "$BACKUP_KEEP_DAILY" \
    --keep-weekly "$BACKUP_KEEP_WEEKLY" \
    --keep-monthly "$BACKUP_KEEP_MONTHLY"
if [ "$BACKUP_PRUNE" = "true" ]; then
    set -- "$@" --prune
fi
"$@"

state_tmp="$BACKUP_STATE_DIR/last-success.tmp"
date +%s > "$state_tmp"
mv "$state_tmp" "$BACKUP_STATE_DIR/last-success"
log info backup_completed "database=$PGDATABASE repository=$RESTIC_REPOSITORY"
