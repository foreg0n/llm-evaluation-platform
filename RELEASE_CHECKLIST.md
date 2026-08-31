# Evalflow v1.0 Release Checklist

This checklist is the final gate after v0.37.0. Automated checks are enforced
in CI; the remaining product-review items should be completed before the
planned v1.0.0 tag.

## Automated Quality Gates

- [x] Backend tests do not call real provider APIs.
- [x] Frontend lint, production build, and component tests run in CI.
- [x] The complete Alembic migration chain renders in CI.
- [x] Development, production, and backup Compose configurations are validated.
- [x] Production API, frontend, and backup images build in CI.
- [x] Encrypted backup and isolated restore drills run in CI.
- [x] Version consistency, migration topology, and repository hygiene are
  checked by `python scripts/release_audit.py`.

## Final Product Review

- [ ] Apply and review the final UX/UI correction list on desktop and mobile.
- [ ] Complete keyboard-only navigation and visible-focus review.
- [ ] Confirm readable empty, loading, error, and long-content states.
- [ ] Capture current screenshots after the UI is frozen.
- [ ] Run the guided workflow in `docs/DEMO.md` with two real models.
- [ ] Review provider costs and remove any credentials used for the demo.

## Tagging v1.0.0

- [ ] Confirm `git status` is clean and CI is green on `main`.
- [ ] Move relevant entries from **Unreleased** in `CHANGELOG.md` to `1.0.0`.
- [ ] Set the application version and release examples to `1.0.0`.
- [ ] Run `python scripts/release_audit.py` locally.
- [ ] Create and push the annotated `v1.0.0` tag.
- [ ] Verify the API, frontend, and backup images in GHCR.
