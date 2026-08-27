# Production Host Bootstrap

This directory prepares a fresh, supported Ubuntu VPS without selecting a
specific cloud provider. The bootstrap installs Docker Engine from Docker's
official apt repository, enables fail2ban and unattended security upgrades,
creates a dedicated deployment account, and prepares `/opt/evalflow`.

Supported Ubuntu releases are 22.04, 24.04, and 26.04. Start with a fresh server
and configure the provider firewall for the chosen SSH port, TCP `80/443`, and
UDP `443`. Do not expose PostgreSQL, Redis, API, or worker metrics ports.

Generate a dedicated deployment key on the administrator workstation:

```bash
ssh-keygen -t ed25519 -f ./evalflow-production -C evalflow-production
```

Copy the repository to the server or download the exact tagged source, then run:

```bash
sudo EVALFLOW_SSH_PUBLIC_KEY="$(cat ./evalflow-production.pub)" \
  EVALFLOW_SSH_PORT=22 \
  bash infra/provision-ubuntu.sh
```

The script is idempotent and refuses to remove conflicting distribution Docker
packages automatically. If it reports a conflict, review and remove those
packages explicitly using Docker's current Ubuntu installation guide.

The deployment user belongs to the `docker` group, which is effectively
root-equivalent. Use this key only for deployment, protect the private key, do
not reuse a personal SSH key, and rotate it after suspected exposure.

After provisioning, collect the server host-key line from a trusted console:

```bash
ssh-keyscan -p 22 your-server.example.com
```

Verify its fingerprint through the cloud-provider console before saving the
complete line as the GitHub Environment secret `DEPLOY_SSH_KNOWN_HOSTS`. The
workflow deliberately never runs `ssh-keyscan` on an untrusted network.
