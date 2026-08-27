# Production Deployment

This runbook deploys Evalflow to one Linux server with Docker Compose. Caddy is
the only public service: it terminates HTTPS and routes same-origin browser API
requests to FastAPI. PostgreSQL, Redis, the worker, and their metrics endpoints
have no host ports.

## 1. Provision a fresh server

Start with Ubuntu 22.04, 24.04, or 26.04. Point a DNS `A` record (and an `AAAA`
record when IPv6 is configured) for your hostname to the server. In the cloud
firewall allow the chosen SSH port, TCP `80/443`, and UDP `443` for HTTP/3. Do
not expose PostgreSQL, Redis, the API, or worker metrics ports.

Generate a dedicated ED25519 deployment key on the administrator workstation.
Do not reuse a personal key:

```bash
ssh-keygen -t ed25519 -f ./evalflow-production -C evalflow-production
```

Obtain the exact tagged repository source on the server and run the idempotent
bootstrap through its console or an existing administrative SSH session:

```bash
sudo EVALFLOW_SSH_PUBLIC_KEY="$(cat ./evalflow-production.pub)" \
  EVALFLOW_SSH_PORT=22 \
  bash infra/provision-ubuntu.sh
```

It installs Docker Engine and Compose from Docker's official Ubuntu repository,
enables fail2ban and unattended security updates, creates the locked `evalflow`
account, and prepares `/opt/evalflow`. It refuses to remove conflicting Docker
packages automatically. See [infra/README.md](infra/README.md) for the bounded
manual resolution and host-key verification procedure.

The deployment account belongs to the `docker` group and is therefore
root-equivalent. Protect and rotate its private key accordingly.

## 2. Configure the GitHub production Environment

In the repository, open **Settings → Environments → New environment** and name
it `production`. Add a required reviewer, prevent self-review when the plan
supports it, and restrict deployment branches/tags to the release policy.

Add these Environment variables:

- `APP_DOMAIN`: the public hostname without `https://`;
- `DEPLOY_HOST`: the verified server hostname or IP;
- `DEPLOY_PORT`: the SSH port, normally `22`;
- `DEPLOY_USER`: the provisioned account, normally `evalflow`.

Add these Environment secrets:

- `DEPLOY_SSH_PRIVATE_KEY`: the complete dedicated private key;
- `DEPLOY_SSH_KNOWN_HOSTS`: the complete, independently verified host-key line;
- `PRODUCTION_ENV_FILE`: the complete production dotenv file described below.

Collect the host-key line from a trusted workstation, verify its fingerprint in
the cloud console, and only then store it. The workflow intentionally does not
trust a live `ssh-keyscan` result during deployment.

## 3. Prepare the production environment

Copy `.env.production.example` locally and replace every placeholder. The
deployment workflow rewrites the three image values to the approved version, so
they remain useful only for local validation.

Generate independent secrets. The hexadecimal output is URL-safe and can be
used for the database, Redis, and JWT signing values:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the real domain, email, SMTP configuration, and independent application,
backup, and storage secrets. Save the complete content as the Environment secret
`PRODUCTION_ENV_FILE`; never commit it. Keep a secure backup of
`CREDENTIAL_ENCRYPTION_KEY`; losing it makes stored provider credentials
unreadable.

Validate interpolation locally before storing it or changing any running
containers:

```bash
docker compose --env-file .env.production -f compose.production.yaml config --quiet
```

## 4. Publish and deploy a release

Commit and push the release-ready code, then create a semantic version tag:

```bash
git switch main
git pull --ff-only
git tag -a v0.34.0 -m "Evalflow v0.34.0"
git push origin v0.34.0
```

Wait for **Release container images** to succeed. Then open **Actions → Deploy
production → Run workflow**, enter `0.34.0` and the literal confirmation
`deploy-production`, and approve the `production` Environment review.

The workflow checks out the exact tag, verifies the API/frontend/backup image
manifests, pins the SSH host identity, and invokes the server-side deployment
script. The script validates the candidate environment before changing the
active file, takes an on-demand backup when an existing stack is present, pulls
the exact images, starts the dependency-ordered stack, verifies the migration
exit code and all seven long-running services, then checks public HTTPS. A
filesystem lock prevents two deployments from running at once.

Inspect status without exposing secrets:

```bash
docker compose --env-file .env.production -f compose.production.yaml logs --tail=200 migrate api worker frontend caddy
curl -fsS https://evalflow.example.com/health
```

The one-shot `migrate` service must finish with exit code `0`; all long-running
services must be healthy. `/ready`, `/metrics`, API documentation, PostgreSQL,
Redis, and worker metrics intentionally remain private in this topology.

## 5. Manual deployment fallback

If GitHub Actions is unavailable, copy the exact tagged `compose.production.yaml`,
`deploy/Caddyfile`, and `deploy/scripts/deploy-production.sh` into
`/opt/evalflow`; write the reviewed dotenv content to
`.env.production.incoming` with mode `0600`; then invoke the same guarded script:

```bash
cd /opt/evalflow
chmod 0555 deploy/scripts/deploy-production.sh
deploy/scripts/deploy-production.sh 0.34.0 foreg0n/llm-evaluation-platform
```

For a public repository, make all three GHCR packages public or grant the server
read access and run `docker login ghcr.io` before `pull`.

## 6. Upgrade and recover

The protected deployment performs the freshness check and on-demand recovery
point automatically. Operators can also run both checks manually:

```bash
docker compose --env-file .env.production -f compose.production.yaml exec backup health
docker compose --env-file .env.production -f compose.production.yaml run --rm backup backup
```

The server preserves the previous dotenv file at
`/opt/evalflow/.env.production.previous`. It does not roll back automatically:
database migrations are forward-only, and blindly restoring old containers may
be incompatible with the new schema. For an application-only failure with a
compatible schema, review the previous file and deliberately redeploy the prior
tag. For an incompatible migration, follow the release-specific database
recovery plan and restore a verified snapshot during a maintenance window.

## 7. Backups and restore drills

Use a bucket outside the application server. Restrict its credentials to the
backup prefix, enable provider-side versioning or object lock when available,
and alert when the `backup` container is unhealthy. The default policy retains
7 daily, 5 weekly, and 12 monthly snapshots; adjust it to legal and business
recovery requirements.

The restic password is the repository encryption key. Store it in a different
secret system from the object-storage credentials. Also back up
`CREDENTIAL_ENCRYPTION_KEY` independently because saved provider API keys remain
Fernet-encrypted inside PostgreSQL dumps.

List encrypted snapshots:

```bash
docker compose --env-file .env.production -f compose.production.yaml run --rm backup restic snapshots --tag evalflow-postgres
```

Run at least one restore drill after initial deployment and on a schedule:

```bash
docker compose --env-file .env.production -f compose.production.yaml \
  --profile restore up --abort-on-container-exit \
  --exit-code-from restore-drill restore-drill
docker compose --env-file .env.production -f compose.production.yaml \
  --profile restore rm -f restore-drill restore-postgres
```

The drill uses a tmpfs-backed target database and never connects `pg_restore`
to the live PostgreSQL service. Success requires a readable restic repository,
a complete custom-format dump, a non-empty Alembic version, and at least the
configured number of public tables. A real disaster recovery still requires a
planned maintenance window, a new empty target database, application shutdown,
and validation before traffic is switched.

## 8. Operations

Follow application and backup logs:

```bash
docker compose --env-file .env.production -f compose.production.yaml logs -f api worker backup caddy
```

Stop containers while preserving PostgreSQL, Redis, and Caddy data:

```bash
docker compose --env-file .env.production -f compose.production.yaml down
```

Do not add `-v` unless permanent deletion of all production volumes is
intentional and a verified backup exists.
