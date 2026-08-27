# Production Deployment

This runbook deploys Evalflow to one Linux server with Docker Compose. Caddy is
the only public service: it terminates HTTPS and routes same-origin browser API
requests to FastAPI. PostgreSQL, Redis, the worker, and their metrics endpoints
have no host ports.

## 1. Prepare the server

Install Docker Engine with the Compose plugin. Point a DNS `A` record (and an
`AAAA` record when IPv6 is configured) for your hostname to the server. Allow
inbound TCP ports `80` and `443`; allow UDP `443` for HTTP/3.

Clone the repository and create the private environment file:

```bash
git clone https://github.com/foreg0n/llm-evaluation-platform.git
cd llm-evaluation-platform
cp .env.production.example .env.production
chmod 600 .env.production
```

Generate independent secrets. The hexadecimal output is URL-safe and can be
used for the database, Redis, and JWT signing values:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Edit `.env.production`. Set the real domain, email, SMTP configuration, image
tags, and independent application, backup, and storage secrets. Never commit this file. Keep a secure backup of
`CREDENTIAL_ENCRYPTION_KEY`; losing it makes stored provider credentials
unreadable.

## 2. Validate and start

Validate interpolation before changing any running containers:

```bash
docker compose --env-file .env.production -f compose.production.yaml config --quiet
```

Pull the immutable release images and start the stack:

```bash
docker compose --env-file .env.production -f compose.production.yaml pull
docker compose --env-file .env.production -f compose.production.yaml up -d
docker compose --env-file .env.production -f compose.production.yaml ps -a
```

The one-shot `migrate` service must finish with exit code `0`. The other six
services should become healthy. Inspect startup without exposing secrets:

```bash
docker compose --env-file .env.production -f compose.production.yaml logs --tail=200 migrate api worker frontend caddy
curl -fsS https://evalflow.example.com/health
```

Replace the example hostname in the final command. `/ready`, `/metrics`, the
API documentation, PostgreSQL, Redis, and worker metrics intentionally remain
private in this topology.

## 3. Publish a release

The release workflow runs the complete CI suite before publishing multi-arch
API and frontend images to GitHub Container Registry. It starts only for a
semantic version tag:

```bash
git switch main
git pull --ff-only
git tag -a v0.32.0 -m "Evalflow v0.32.0"
git push origin v0.32.0
```

After the **Release container images** workflow succeeds, set all three image values
in `.env.production` to the new exact version, then run `pull` and `up -d`
again. The frontend release image uses same-origin `/api` requests, so it is
portable across domains behind Caddy.

For a public repository, make all three GHCR packages public or grant the server
read access and run `docker login ghcr.io` before `pull`.

## 4. Upgrade and roll back

The v0.32 stack creates encrypted PostgreSQL backups automatically, but verify
freshness and create an on-demand recovery point before every upgrade:

```bash
docker compose --env-file .env.production -f compose.production.yaml exec backup health
docker compose --env-file .env.production -f compose.production.yaml run --rm backup backup
```

To deploy a newer version, change all three image tags, validate, pull, and
recreate the services:

```bash
docker compose --env-file .env.production -f compose.production.yaml config --quiet
docker compose --env-file .env.production -f compose.production.yaml pull
docker compose --env-file .env.production -f compose.production.yaml up -d
```

To roll back application code, restore all three previous image tags and repeat the
commands. Database migrations are forward-only; if a release includes an
incompatible migration, follow that release's database restore instructions
instead of assuming an image rollback can reverse the schema.

## 5. Backups and restore drills

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

## 6. Operations

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
