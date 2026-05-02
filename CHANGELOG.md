# Changelog

This file records user-visible and operational changes.

Each release entry should explain:

- what changed for the user or operator;
- why the change was needed;
- which important files, APIs, or workflows were affected;
- how the change was verified;
- whether deploy was confirmed through `/health`, when applicable.

## 5.6.0 - 2026-05-03

### Added

- Added batch ZIP upload in the public web UI and API. Users can now select several Tilda export archives in one upload and receive separate processing jobs/download links.
- Added configurable Tilda-export archive validation:
  - default required files are `htaccess`, `sitemap.xml`, `404.html`, `readme.txt`, and `robots.txt`;
  - `htaccess` also accepts `.htaccess`;
  - admins can edit the required file list in the “Конфигурация” card.
- Added domain-based result archive names. The download filename now uses the domain parsed from `robots.txt` (`Host:` first, then `Sitemap:`), for example `example.com.zip`.
- Added a web login screen for `/admin` so the browser no longer shows the native HTTP Basic authentication alert.
- Added admin password management in the web UI:
  - the “Безопасность” card contains a password-change form;
  - the current password must be confirmed;
  - the new password must be at least 8 characters;
  - after a successful change, the browser updates its stored admin API token.
- Added protected admin API endpoint:
  - `POST /admin/api/password`.

### Changed

- `/admin` now serves the admin shell without requiring HTTP Basic at the page level.
- `/admin/api/*` routes remain protected by HTTP Basic credentials.
- `POST /api/jobs` now returns a `jobs` array for batch requests while preserving the legacy `job_id/status` fields for a single uploaded archive.
- Staging and production Docker Compose files now mount the server-local env file into the container as `/app/.env.runtime`.
- `ADMIN_ENV_FILE=/app/.env.runtime` lets the app persist `ADMIN_PASSWORD` back to the server-local env file, so the changed password survives container restarts and future deploys.

### Tests

- Added web API tests for:
  - `/admin` serving the web login page;
  - `/admin/api/stats` still requiring authentication;
  - password changes updating runtime authentication;
  - password changes preserving unrelated env-file lines;
  - rejecting an incorrect current password.
- Added web API tests for:
  - multiple archive upload;
  - rejecting archives that do not contain required Tilda export files;
  - editing required archive files from admin config;
  - result download filename based on `robots.txt`.
- Ran `python -m pytest tests/test_web_api.py -q`: `28 passed`.
- Ran `python -m pytest tests/ -q`: `318 passed, 2 warnings`.
- Verified `/admin` in a local browser runtime:
  - login overlay is visible before authentication;
  - valid credentials hide the login overlay and load the dashboard;
  - browser console errors/warnings list is empty.
- Verified `/` in a local browser runtime:
  - the file input has `multiple`;
  - the page loads without browser console errors/warnings.

## 5.5.2 - 2026-05-02

### Fixed

- Fixed staging/prod deploy after `.env.staging` and `.env.prod` were removed from git.
- The deploy workflow now removes the server-local env file from the working tree before `git checkout/reset`, then restores it after checkout.
- This prevents Git from aborting with “local changes would be overwritten by checkout” for `.env.staging` or `.env.prod`.

### Changed

- Updated `.github/workflows/deploy.yml` so server-local env files remain untracked secrets, while deploy still has the env file required by Docker Compose.

### Verified

- Ran `python -m pytest tests/ -q`: `311 passed, 2 warnings`.
- Pushed `main` and tag `v5.5.2`.
- Confirmed staging deploy through `https://detilda.proskurnin.com/health`: version `5.5.2`.

## 5.5.1 - 2026-05-02

### Fixed

- Added initial deploy workflow handling for server-local `.env.staging` and `.env.prod`.
- The workflow backs up an existing env file from the deploy directory or from `/home/deploy/.env.*` / `/home/deploy/secrets/.env.*`, then restores it after `git reset --hard`.

### Context

- This was needed because `.env.staging` and `.env.prod` were intentionally removed from git history tracking, but `docker-compose.staging.yml` and `docker-compose.prod.yml` still require local env files at runtime.
- The first implementation preserved the env file but still left it in the working tree before checkout, which was fully fixed in `5.5.2`.

## 5.5.0 - 2026-05-02

### Added

- Added clickable processing-result metrics in the public web UI.
- Each result row now opens a details modal:
  - renamed files;
  - fixed links;
  - CDN downloads;
  - hooked forms;
  - warnings;
  - errors.
- Added structured `stats.details` to the job API response so the frontend can show details without parsing raw text.
- Added warning/error extraction from per-job deTilda logs for display in the details modal.
- Added admin pagination for the “Задачи” table.
- Added a new “Логи” column in the admin job table.
- Added per-job log viewing in an admin modal.
- Added protected admin API endpoint for reading a job log:
  - `GET /admin/api/jobs/{job_id}/log`.

### Changed

- `GET /admin/api/jobs` now returns paginated data instead of a bare array:
  - `items`;
  - `total`;
  - `page`;
  - `page_size`;
  - `pages`.
- Admin job rows now expose whether a log is available and its size:
  - `log_available`;
  - `log_size`.

### Fixed

- Fixed the cleanup status message in the admin UI to show separate removed job and log counts instead of referencing a non-existent `removed` field.

### Tests

- Added `tests/test_web_worker_details.py` for processing-result details and warning/error log extraction.
- Added web API tests for:
  - admin job pagination;
  - per-job log retrieval;
  - missing-log `404` behavior.
- Ran `python -m pytest tests/ -q`: `311 passed, 2 warnings`.

### Deploy

- Pushed `main` and tag `v5.5.0`.
- Deploy was blocked by the server-local env-file checkout issue, later fixed in `5.5.1` and `5.5.2`.

## 5.4.7 - 2026-05-02

- Patched Zero Forms dynamic resource loading to use the local script directory instead of `static.aidacdn`.

## 5.4.6 - 2026-05-02

- Fixed Zero Forms runtime dependency handling so horizontal/errorbox CSS and fallback JS are bundled when CDN access is unavailable.
- Added form checks for missing Zero Forms runtime dependencies.
- Guarded optional SmoothScroll initialization to avoid a console `ReferenceError` when the external script is unavailable.

## 5.4.5 - 2026-05-02

- Added retry loop to deploy health checks so freshly restarted containers can become ready before the workflow fails.
- Verified staging health endpoint returns `5.4.5`.

## 5.4.4 - 2026-05-02

- Fixed staging/prod repository ownership before deploy `git fetch`.
- Confirmed the previous deploy failure was caused by `.git/objects` permission errors on the server.

## 5.4.3 - 2026-05-02

- Improved SSH deploy shell compatibility by avoiding `pipefail` in the remote script.
- Added hard reset to remote branch state during deploy.

## 5.4.2 - 2026-05-02

- Fixed CDN localization corrupting dynamic Tilda Zero Forms runtime URLs.
- Added regression coverage to ensure dynamic CDN bases in zero-forms JS are not rewritten as local resources.
- Confirmed `aida-zero-forms-1.0.min.js` remains syntactically valid after processing.

## 5.4.1 - 2026-05-02

- Hardened deploy workflow so staging/prod check out the exact remote branch state.
- Added manual workflow dispatch support.

## 5.4.0 - 2026-05-02

- Added Zero Forms namespace bridge so `ai_zeroForms__init` and legacy `t_zeroForms__init` can interoperate after namespace rewriting.
