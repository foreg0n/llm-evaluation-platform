# Changelog

All notable changes to Evalflow are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- Updated Vinext and its RSC plugin together and grouped their future
  Dependabot updates so locked installs keep peer dependencies compatible.
- Synchronized React client, DOM, server-component, and type packages, and
  deferred TypeScript and ESLint majors unsupported by the current linting
  toolchain.
- Made temporary PostgreSQL dump creation compatible with Alpine BusyBox so
  the encrypted backup and isolated restore CI drill can run end to end.
- Replaced the visually unchanged authentication split-screen with a visibly
  distinct evaluation-workspace entry screen, workflow map, compact access
  card, system status chrome, and dedicated mobile layout.
- Reorganized authenticated navigation into workspace and configuration groups
  and tightened dashboard headers, metrics, tables, and interactive states.
- Consolidated dataset creation and file import into one action pair in the
  Collections panel, removing duplicate controls from the page header and
  empty state.

## [0.37.0] - 2026-08-31

### Added

- Outbound custom-provider endpoint validation that blocks cloud metadata,
  link-local, reserved, and unsafe resolved addresses while preserving local
  Ollama and private-network deployments.
- Ruff linting and complexity checks for backend, evaluation, test, and release
  tooling, enforced by CI.
- A production-only npm vulnerability gate and regression tests for endpoint
  security, password-reset persistence, and cancellation logging.

### Changed

- The web application now uses a compact near-black developer-tool design
  system with one accent, flat data surfaces, visible keyboard focus, dense
  tables, skeleton loading, and a collapsible sidebar.
- Shared dialogs, status badges, loading states, navigation, run exports, and
  comparison utilities were extracted from the two largest frontend modules.
- Starlette tests now use `httpx2`; backend run execution and the release audit
  were decomposed to stay below the configured complexity limit.
- The unused Cloudflare Worker/OpenAI Sites starter files and dependencies were
  removed from the Vinext production path.
- Authentication transactions and non-fatal operational failures now have
  explicit commit or structured logging ownership.

## [0.36.0] - 2026-08-30

### Added

- A deterministic 15-case portfolio benchmark and five-minute demo guide.
- An automated release audit for version drift, migration topology, accidental
  secrets, generated files, merge markers, and incomplete student tasks.
- Contributor, security, release-checklist, and pull-request documentation.

### Changed

- CI now runs the repository release audit before the network-free test suite.
- Project metadata and release examples now target v0.36.0.

## [0.35.0] - 2026-08-30

### Added

- Server-side pagination, filtering, and sorting for evaluation results.
- Incremental loading for large imported datasets.
- SQL-computed run summaries and pagination indexes.

## [0.34.0] - 2026-08-30

### Added

- Credential-scoped provider model discovery with caching and safe fallbacks.
- Searchable model selection with manual model-ID entry.

## [0.31.0 - 0.33.0]

### Added

- Production containers, automatic HTTPS, GHCR release automation, encrypted
  backups, restore drills, VPS provisioning, and protected deployment gates.

## [0.27.0 - 0.30.0]

### Added

- Multi-provider BYOK credentials encrypted at rest, account recovery,
  verification email, privacy-safe error monitoring, and distributed tracing.

## [0.1.0 - 0.26.0]

### Added

- The evaluation core, provider abstraction, async runner, metrics, FastAPI and
  PostgreSQL backend, authentication, Celery execution, full web workflow,
  analytics, exports, comparisons, observability, and continuous integration.

[Unreleased]: https://github.com/foreg0n/llm-evaluation-platform/compare/v0.37.0...HEAD
[0.37.0]: https://github.com/foreg0n/llm-evaluation-platform/compare/v0.36.0...v0.37.0
[0.36.0]: https://github.com/foreg0n/llm-evaluation-platform/compare/v0.35.0...v0.36.0
[0.35.0]: https://github.com/foreg0n/llm-evaluation-platform/compare/v0.34.0...v0.35.0
[0.34.0]: https://github.com/foreg0n/llm-evaluation-platform/releases/tag/v0.34.0
