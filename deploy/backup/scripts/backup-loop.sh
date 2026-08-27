#!/bin/sh

set -eu

. /opt/evalflow-backup/common.sh

BACKUP_INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"
BACKUP_RETRY_SECONDS="${BACKUP_RETRY_SECONDS:-300}"
BACKUP_RUN_ON_START="${BACKUP_RUN_ON_START:-true}"

require_positive_integer BACKUP_INTERVAL_SECONDS
require_positive_integer BACKUP_RETRY_SECONDS

trap 'log info backup_loop_stopping; exit 0' HUP INT TERM

if [ "$BACKUP_RUN_ON_START" != "true" ]; then
    log info backup_loop_waiting "seconds=$BACKUP_INTERVAL_SECONDS"
    sleep "$BACKUP_INTERVAL_SECONDS"
fi

while true; do
    if /opt/evalflow-backup/backup-once.sh; then
        wait_seconds="$BACKUP_INTERVAL_SECONDS"
    else
        wait_seconds="$BACKUP_RETRY_SECONDS"
        log error backup_failed "retry_seconds=$wait_seconds"
    fi
    sleep "$wait_seconds"
done
