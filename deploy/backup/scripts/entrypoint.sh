#!/bin/sh

set -eu

case "${1:-loop}" in
    loop)
        exec /opt/evalflow-backup/backup-loop.sh
        ;;
    backup)
        exec /opt/evalflow-backup/backup-once.sh
        ;;
    restore)
        exec /opt/evalflow-backup/restore-drill.sh
        ;;
    health)
        exec /opt/evalflow-backup/healthcheck.sh
        ;;
    *)
        exec "$@"
        ;;
esac
