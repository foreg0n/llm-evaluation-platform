#!/bin/sh

set -eu

. /opt/evalflow-backup/common.sh

BACKUP_STATE_DIR="${BACKUP_STATE_DIR:-/state}"
BACKUP_MAX_AGE_SECONDS="${BACKUP_MAX_AGE_SECONDS:-90000}"
require_positive_integer BACKUP_MAX_AGE_SECONDS

state_file="$BACKUP_STATE_DIR/last-success"
if [ ! -f "$state_file" ]; then
    log error backup_health_failed reason=no_successful_backup
    exit 1
fi

last_success="$(cat "$state_file")"
case "$last_success" in
    ''|*[!0-9]*)
        log error backup_health_failed reason=invalid_state
        exit 1
        ;;
esac

age_seconds="$(( $(date +%s) - last_success ))"
if [ "$age_seconds" -lt 0 ] || [ "$age_seconds" -gt "$BACKUP_MAX_AGE_SECONDS" ]; then
    log error backup_health_failed "age_seconds=$age_seconds max_age_seconds=$BACKUP_MAX_AGE_SECONDS"
    exit 1
fi

log info backup_health_ok "age_seconds=$age_seconds"
