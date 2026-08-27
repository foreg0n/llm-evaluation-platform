#!/usr/bin/env bash

set -Eeuo pipefail

log() {
    printf '%s level=%s event=%s %s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "${3:-}"
}

if [[ "${EUID}" -ne 0 ]]; then
    log error root_required "Run this script through sudo or as root."
    exit 1
fi

exec 9>/var/lock/evalflow-provision.lock
if ! flock -n 9; then
    log error provision_locked "Another provisioning process is running."
    exit 1
fi

DEPLOY_USER="${EVALFLOW_DEPLOY_USER:-evalflow}"
DEPLOY_PUBLIC_KEY="${EVALFLOW_SSH_PUBLIC_KEY:-}"
SSH_PORT="${EVALFLOW_SSH_PORT:-22}"

if [[ ! "$DEPLOY_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
    log error invalid_deploy_user "value=$DEPLOY_USER"
    exit 1
fi
if [[ ! "$SSH_PORT" =~ ^[0-9]+$ ]] || (( SSH_PORT < 1 || SSH_PORT > 65535 )); then
    log error invalid_ssh_port "value=$SSH_PORT"
    exit 1
fi
if [[ ! "$DEPLOY_PUBLIC_KEY" =~ ^(ssh-ed25519|sk-ssh-ed25519@openssh.com|ssh-rsa)[[:space:]] ]]; then
    log error invalid_public_key "Set EVALFLOW_SSH_PUBLIC_KEY to one dedicated public key."
    exit 1
fi
if [[ "$DEPLOY_PUBLIC_KEY" == *$'\n'* || "$DEPLOY_PUBLIC_KEY" == *$'\r'* ]]; then
    log error invalid_public_key "The public key must occupy exactly one line."
    exit 1
fi

source /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
    log error unsupported_os "id=${ID:-unknown}; expected=ubuntu"
    exit 1
fi
case "${VERSION_ID:-}" in
    22.04|24.04|26.04) ;;
    *)
        log error unsupported_ubuntu "version=${VERSION_ID:-unknown}"
        exit 1
        ;;
esac

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl fail2ban gnupg unattended-upgrades

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    conflicts=()
    for package in docker.io docker-compose docker-compose-v2 podman-docker containerd runc; do
        if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
            conflicts+=("$package")
        fi
    done
    if (( ${#conflicts[@]} > 0 )); then
        log error conflicting_docker_packages "packages=${conflicts[*]}"
        printf 'Remove the conflicting packages explicitly, then rerun provisioning.\n' >&2
        exit 1
    fi

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    architecture="$(dpkg --print-architecture)"
    printf '%s\n' \
        'Types: deb' \
        'URIs: https://download.docker.com/linux/ubuntu' \
        "Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}" \
        'Components: stable' \
        "Architectures: $architecture" \
        'Signed-By: /etc/apt/keyrings/docker.asc' \
        > /etc/apt/sources.list.d/docker.sources

    apt-get update
    apt-get install -y \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
fi

systemctl enable --now docker

if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash "$DEPLOY_USER"
fi
usermod --append --groups docker "$DEPLOY_USER"
passwd --lock "$DEPLOY_USER" >/dev/null 2>&1 || true

deploy_home="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
install -d -m 0700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$deploy_home/.ssh"
printf '%s\n' "$DEPLOY_PUBLIC_KEY" > "$deploy_home/.ssh/authorized_keys"
chown "$DEPLOY_USER:$DEPLOY_USER" "$deploy_home/.ssh/authorized_keys"
chmod 0600 "$deploy_home/.ssh/authorized_keys"

install -d -m 0750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /opt/evalflow
printf '%s\n' \
    '[sshd]' \
    'enabled = true' \
    "port = $SSH_PORT" \
    'backend = systemd' \
    > /etc/fail2ban/jail.d/evalflow-sshd.local
systemctl enable --now fail2ban unattended-upgrades

docker version --format 'Docker Engine {{.Server.Version}}'
docker compose version
log info provision_completed "deploy_user=$DEPLOY_USER app_dir=/opt/evalflow"
printf '%s\n' \
    'Configure the cloud firewall for the selected SSH port plus TCP 80/443' \
    'and UDP 443. The docker group is root-equivalent; keep this key dedicated.'
