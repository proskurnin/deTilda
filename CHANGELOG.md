# Changelog

This file records user-visible and operational changes.

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
