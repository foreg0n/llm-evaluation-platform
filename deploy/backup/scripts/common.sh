#!/bin/sh

set -eu

log() {
    level="$1"
    event="$2"
    shift 2
    timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '%s level=%s event=%s' "$timestamp" "$level" "$event"
    if [ "$#" -gt 0 ]; then
        printf ' %s' "$*"
    fi
    printf '\n'
}

require_env() {
    name="$1"
    eval "value=\${$name:-}"
    if [ -z "$value" ]; then
        log error configuration_missing "variable=$name"
        return 1
    fi
}

require_positive_integer() {
    name="$1"
    eval "value=\${$name:-}"
    case "$value" in
        ''|*[!0-9]*|0)
            log error configuration_invalid "variable=$name expected=positive_integer"
            return 1
            ;;
    esac
}

initialize_repository() {
    if restic cat config >/dev/null 2>&1; then
        return 0
    fi

    log warning repository_initializing "repository=$RESTIC_REPOSITORY"
    restic init
    log info repository_initialized "repository=$RESTIC_REPOSITORY"
}
