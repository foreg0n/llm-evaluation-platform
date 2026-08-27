#!/bin/sh

set -eu

. /opt/evalflow-backup/common.sh

require_env RESTIC_REPOSITORY
require_env RESTIC_PASSWORD
require_env TARGET_PGHOST
require_env TARGET_PGDATABASE
require_env TARGET_PGUSER
require_env TARGET_PGPASSWORD

RESTIC_HOST="${RESTIC_HOST:-evalflow-production}"
RESTIC_TAG="${RESTIC_TAG:-evalflow-postgres}"
RESTORE_MIN_PUBLIC_TABLES="${RESTORE_MIN_PUBLIC_TABLES:-8}"
require_positive_integer RESTORE_MIN_PUBLIC_TABLES

restore_dir="$(mktemp -d /tmp/evalflow-restore-XXXXXX)"
trap 'rm -rf "$restore_dir"' EXIT HUP INT TERM

log info restore_drill_started "target=$TARGET_PGHOST/$TARGET_PGDATABASE"
restic check
restic restore latest \
    --host "$RESTIC_HOST" \
    --tag "$RESTIC_TAG" \
    --target "$restore_dir"

dump_path="$(find "$restore_dir" -type f -name 'evalflow-postgres-*.dump' | sort | tail -n 1)"
if [ -z "$dump_path" ]; then
    log error restore_drill_failed reason=dump_not_found
    exit 1
fi

export PGPASSWORD="$TARGET_PGPASSWORD"
pg_isready --quiet \
    --host "$TARGET_PGHOST" \
    --username "$TARGET_PGUSER" \
    --dbname "$TARGET_PGDATABASE"
pg_restore \
    --exit-on-error \
    --no-owner \
    --no-privileges \
    --host "$TARGET_PGHOST" \
    --username "$TARGET_PGUSER" \
    --dbname "$TARGET_PGDATABASE" \
    "$dump_path"

schema_version="$(psql \
    --host "$TARGET_PGHOST" \
    --username "$TARGET_PGUSER" \
    --dbname "$TARGET_PGDATABASE" \
    --tuples-only --no-align \
    --command 'SELECT version_num FROM alembic_version LIMIT 1')"
table_count="$(psql \
    --host "$TARGET_PGHOST" \
    --username "$TARGET_PGUSER" \
    --dbname "$TARGET_PGDATABASE" \
    --tuples-only --no-align \
    --command "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")"

if [ -z "$schema_version" ]; then
    log error restore_drill_failed reason=missing_alembic_version
    exit 1
fi
case "$table_count" in
    ''|*[!0-9]*)
        log error restore_drill_failed reason=invalid_table_count
        exit 1
        ;;
esac
if [ "$table_count" -lt "$RESTORE_MIN_PUBLIC_TABLES" ]; then
    log error restore_drill_failed "reason=too_few_tables tables=$table_count minimum=$RESTORE_MIN_PUBLIC_TABLES"
    exit 1
fi

printf '{"status":"ok","schema_version":"%s","public_tables":%s}\n' \
    "$schema_version" "$table_count"
log info restore_drill_completed "schema_version=$schema_version public_tables=$table_count"
