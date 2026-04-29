# AGENTS.md - deTilda

## Purpose
deTilda converts a Tilda ZIP export into a self-hostable site via a deterministic multi-step pipeline.
Primary goals: no Tilda remnants, stable links/assets, reproducible output, clear reports.

## Project Context
- Entry point: `main.py`.
- Orchestration: `core/pipeline.py` (ordered processing steps).
- Global rules/config: `config/config.yaml` plus typed loading via `core/config_loader.py` and `core/schemas.py`.
- Version source of truth: `manifest.json` (SemVer plus release metadata).
- Runtime templates copied into processed sites: `resources/`.

## Engineering Principles
- Prefer minimal, local fixes over broad refactors.
- Preserve pipeline order semantics; changing step order is a breaking behavioral change.
- Keep processing offline-first and deterministic where possible.
- Avoid adding heavy dependencies; project intentionally works without real `pydantic` (see `core/pydantic_compat.py`).
- Backward compatibility first: existing exports and tests should keep working.

## Change Rules
1. If behavior changes, update tests in `tests/` in the same PR.
2. For new config fields, update both schema/loader and defaults/docs.
3. For path/link logic changes, verify HTML/CSS/JS reference updates and edge cases (`.htaccess`, anchors, lazyload images).
4. Do not hardcode project-specific domains/paths in core logic.
5. Keep logs/reports informative; do not silently swallow critical processing errors.

## Validation Checklist
- Run `python -m pytest tests/ -q` before finalizing.
- If version changed, ensure `manifest.json` fields are consistent: `version`, `release_date`, `build.package_name`.

## CLI Agent Guidance
- When touching pipeline-related code, review neighboring step modules for cross-step side effects.
- Prefer small commits with explicit intent (`fix`, `refactor`, `test`, `chore`).
- Never commit generated runtime artifacts from `_workdir/` or transient logs from `logs/`.
