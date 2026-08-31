# Security Policy

## Supported Version

Security fixes are applied to the latest code on the `main` branch. Older tags
are retained as project history and are not maintained as separate release
lines.

## Reporting a Vulnerability

Please do not disclose a suspected vulnerability in a public issue. Use the
repository's **Security** tab to submit a private vulnerability report. Include
the affected component, impact, reproduction conditions, and any suggested
remediation. Do not include real provider credentials, account passwords, or
production data.

Reports concerning authentication, cross-account data access, credential
encryption, secret exposure, or remote code execution receive the highest
priority. Acknowledgement and remediation timing depend on project-maintainer
availability; this personal project does not provide a formal SLA or bug
bounty.

## Operational Responsibility

Evalflow is self-hosted software that makes requests with user-supplied API
keys. Operators are responsible for TLS, secret generation, database and
backup access, provider spending limits, dependency updates, and monitoring.
Use `.env.production.example` only as a template and replace every placeholder
before exposing an instance to the internet.

Custom provider URLs are checked before discovery, credential tests, and
evaluation runs. Known cloud metadata hosts plus link-local, reserved,
unspecified, and multicast addresses are rejected after DNS resolution. Local
loopback and RFC 1918 endpoints remain available for trusted Ollama or internal
gateway deployments; operators must still restrict who can create credentials
and apply network-level egress controls in multi-user environments.
