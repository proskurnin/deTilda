# Changelog

This file records user-visible and operational changes.

Each release entry should explain:

- what changed for the user or operator;
- why the change was needed;
- which important files, APIs, or workflows were affected;
- how the change was verified;
- whether deploy was confirmed through `/health`, when applicable.

## Unreleased

### Added

- Nothing yet.

### Changed

- Nothing yet.

### Verified

- Nothing yet.

## 5.7.7 - 2026-07-17

### Added

- Saved the post-`5.7.6` verification context and follow-up release plan in
  `TODO.md`, including Stage/Prod health checks, relevant commits, and the next
  diagnostics workflow for `input/raizel.ltd.zip`.

### Changed

- Published a patch release after completing the planned Stage flow, problem
  archive, zero-block diagnostics, and multi-file upload UX checks.

### Verified

- Ran `python -m pytest tests/ -q`: `346 passed, 2 warnings`.

## 5.7.6 - 2026-07-17

### Added

- Nothing yet.

### Changed

- Published a patch release to redeploy the current `5.7.5` code state through
  the standard Stage and Prod pipeline.

### Verified

- Ran `python -m pytest tests/ -q`: `346 passed, 2 warnings`.

## 5.7.5 - 2026-07-17

### Added

- Added job details in the public “Мои задачи” list: users can open a modal with
  status, current pipeline step, validation details, progress, warnings, and errors.
- Added `processing_report.json` generation for each queued web job with input
  filename/domain, deTilda version, email/GA parameters, progress, validation,
  warnings, errors, result availability, and error reason when applicable.
- Added a protected public report download endpoint and “отчёт” action in
  “Мои задачи” for downloading each job's `processing_report.json`.

### Changed

- Nothing yet.

### Verified

- Ran `python -m pytest tests/test_web_api.py tests/test_web_worker_details.py -q`: `43 passed`.
- Ran `python -m pytest tests/ -q`: `346 passed, 2 warnings`.

## 5.7.4 - 2026-07-16

### Added

- Added per-file upload settings for multi-file public processing: users can keep
  one shared form email / Google Analytics Measurement ID, or enable an iOS-style
  toggle and set unique email and GA4 IDs for each uploaded ZIP.
- Added `info@` helper buttons next to public upload email fields; they fill the
  email from the selected ZIP filename without its `.zip` extension.

### Changed

- Nothing yet.

### Verified

- Ran `python -m pytest tests/test_web_api.py -q`: `36 passed`.
- Ran `python -m pytest tests/ -q`: `341 passed, 2 warnings`.

## 5.7.3 - 2026-07-16

### Changed

- CDN localization now downloads renamed `aida-*` resources from their original
  `tilda-*` URLs directly, avoiding guaranteed 404 attempts against nonexistent
  `aida-*` files on `static.tildacdn.com`.
- The public “Мои задачи” list now shows the user-facing error reason and hint
  for failed jobs instead of only the generic `ошибка` status.

### Verified

- Ran `python -m pytest tests/test_cdn_localizer.py tests/test_web_api.py::test_index_renders_my_jobs_error_details tests/test_web_worker_details.py -q`: `27 passed`.
- Ran `python -m pytest tests/test_cdn_localizer.py tests/test_web_api.py -q`: `57 passed`.
- Ran `python -m pytest tests/ -q`: `338 passed, 2 warnings`.
- Reprocessed `input/raizel.ltd.zip` and confirmed old `aida-*` CDN warnings and
  `Unresolved URL: https://static.tildacdn.com/js/` are absent.

## 5.7.2 - 2026-07-16

### Changed

- Fixed zero-block form runtime smoke-check so exports with `tilda-zero-1.1.min.js` +
  `tilda-forms-1.0.min.js`, but without a separate `tilda-zero-forms-1.0.min.js`, are not
  incorrectly blocked.

### Verified

- Ran `python -m pytest tests/test_checker_forms.py -q`: `10 passed`.
- Ran `python -m pytest tests/ -q`: `336 passed, 2 warnings`.
- Reprocessed `input/raizel.ltd.zip`: `errors=0`, `zero_form_smoke_failed=False`, forms `60/60`.

## 5.7.1 - 2026-07-16

### Added

- Added public user registration/login with bearer sessions. Public processing endpoints now require a registered user, and each user can see/download only their own jobs.
- Added a personal-account section on the public web UI with current user, logout, upload form, and recent user jobs.
- Added a Google Analytics Measurement ID field to the public upload form. The value is written to generated `js/ga-config.js`; invalid or empty values keep GA4 disabled.
- Added deeper Tilda ZIP validation before queueing jobs:
  - required files are still checked first;
  - at least one non-`404.html` HTML page is required;
  - `data-aida-export="yes"` / `data-tilda-project-id` markers are detected;
  - asset folders referenced by HTML are checked;
  - validation details are exposed in result stats.
- Added offline zero-block form runtime smoke-check for processed `js/aida-zero-forms-1.0.min.js`; critical failures block archive delivery.
- Added `tools/smoke_test_health.py` for comparing expected `manifest.json` version against deployed `/health`.
- Added a generated-archive browser-console smoke test. It opens a processed archive with Playwright and fails on browser console/page errors, while skipping cleanly when Chromium is unavailable.

### Changed

- GitHub Actions deploy now verifies public staging `/health` after staging deploy and both public production `/health` endpoints after production deploy.

### Verified

- Ran `python -m pytest tests/test_process_params.py tests/test_forms.py tests/test_checker_forms.py tests/test_web_auth.py tests/test_web_jobs.py tests/test_web_worker_details.py tests/test_web_api.py tests/test_smoke_test_health.py -q`: `65 passed`.
- Ran `python -m pytest tests/ -q`: `334 passed, 2 warnings`.

## 5.7.0 - 2026-05-03

### Added

- Added the “Домен” column to the admin “Задачи” table. The value is parsed from the processed archive `robots.txt` and rendered as an external link that opens in a new tab.
- Added the “Длительность” column to the admin “Задачи” table. It replaces “Завершена” and shows elapsed processing time from job creation to completion, or current elapsed time for unfinished jobs.
- Added production nginx configs for `detilda.com` and `detilda.ru`:
  - `nginx/prod.bootstrap.conf` for the first HTTP-only certificate bootstrap;
  - `nginx/prod.conf` for the final SSL reverse proxy.
- Added `docs/production-deploy.md` with the production rollout procedure, required GitHub secrets, first certificate bootstrap, and release flow.

### Changed

- Production Docker Compose now binds the app to `127.0.0.1:8001` so it can run on the same server as staging without conflicting with staging port `8000`.
- Production GitHub Actions deploy now installs `nginx/prod.conf`, reloads nginx, and checks local health on `127.0.0.1:8001`.
- Staging and production deploy scripts now remove stale `/tmp/detilda.env.*` backup files before copying the server-local env file. This prevents a previous root-owned bootstrap backup from blocking GitHub Actions deploys that run as `deploy`.

### Verified

- Confirmed DNS resolution for `detilda.com` and `detilda.ru`: both resolve to `2.26.31.179`.
- Created and pushed the `prod` branch at commit `4e8aa7043048f536d63b0f03481ed46c0be24559`.
- Created server-local `/home/deploy/.env.prod` on `2.26.31.179` without printing secret values.
- Bootstrapped production checkout in `/home/deploy/prod`.
- Started the production container on `127.0.0.1:8001`.
- Issued the Let's Encrypt certificate for `detilda.com` and `detilda.ru`.
- Installed the final production nginx SSL config.
- Manually deployed production from `origin/prod`.
- Confirmed production health:
  - `https://detilda.com/health`: version `5.6.0`;
  - `https://detilda.ru/health`: version `5.6.0`.
- Confirmed staging health remains available:
  - `https://detilda.proskurnin.com/health`: version `5.6.0`.
- Added and verified a new deploy SSH key for `deploy@2.26.31.179`; `deploy` has passwordless sudo.
- Tested GitHub Actions production deploy secrets with commit `c99a8a4d964e50d7cf5a7fb7fa067842dff8b9c0`; CI tests passed and deploy reached the server, but failed on a stale root-owned `/tmp/detilda.env.prod` file. The deploy workflow now removes stale temp env backups before copying.
- Ran `python -m pytest tests/test_web_api.py -q`: `28 passed`.
- Ran `python -m pytest tests/ -q`: `318 passed`, `2 warnings`.
- Verified `/admin` with Playwright against local FastAPI: headers are `ID`, `Домен`, `Статус`, `Создана`, `Длительность`, `Логи`, `Детали`; browser console errors were empty.

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
