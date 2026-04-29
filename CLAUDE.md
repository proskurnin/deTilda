# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

deTilda is an offline CLI that takes a Tilda ZIP export and produces a self-hostable site. Processing is a deterministic, ordered multi-step pipeline orchestrated by `core/pipeline.py` (`DetildaPipeline.run`). Pipeline order is part of the contract — reordering steps is a breaking behavioral change.

The README/AGENTS/GEMINI docs describe a 14-step pipeline; the actual pipeline now also runs `font_substitute`, `cdn_localizer`, and a `cdn_cleanup` pass. Always check `core/pipeline.py` for the current ordering rather than trusting the docs.

## Commands

```bash
# Run the tool (interactive — prompts for archive name in _workdir/)
python main.py

# Tests (the validation gate; must pass before finalizing changes)
python -m pytest tests/ -q
python -m pytest tests/test_refs_main.py -q          # single file
python -m pytest tests/test_refs_main.py::test_name  # single test

# Bump version (also updates manifest fields and creates a git tag)
python tools/bump_version.py {patch|minor|major}
```

CI (`.github/workflows/tests.yml`) runs `pytest -v` on Python 3.13.

## Architecture notes that aren't obvious from one file

- **`ProjectContext`** (`core/project.py`) is the per-run object threaded through steps. It bundles `project_root`, the typed `config_loader`, and the shared `rename_map`. New step code should take a `ProjectContext`, not raw paths.
- **`rename_map`** is built in step `assets` and consumed by `refs`, `cleaners`, etc. Anything renaming files must update it; anything rewriting links must read it. Skipping this is the typical source of broken-link regressions.
- **`config/config.yaml`** is the single source of processing rules (regex patterns, replace rules like `til→ai`, file extensions, deletion lists, service-file copies). It is loaded into typed objects via `core/config_loader.py` + `core/schemas.py`. New config fields require updates in **both** the schema and any defaults; tests will fail otherwise.
- **`core/pydantic_compat.py`** is an intentional minimal stand-in for Pydantic. Real `pydantic` is **not** a dependency and must not be added — the project ships via PyInstaller and avoids heavy deps. Use the compat module when extending schemas.
- **`manifest.json`** is the source of truth for `version`, `release_date`, `paths.*`, and `build.package_name`. `core/version.py` reads from it; do not hardcode versions elsewhere. `tools/bump_version.py` keeps these fields consistent.
- **Runtime-script protection** (`core/runtime_scripts.py`, `core/script_cleaner.py`): the cleaner removes Tilda inline scripts but must spare media-runtime markers. When touching `script_cleaner` or its config, run `tests/test_script_cleaner_tilda_media.py` and `tests/test_assets_runtime_scripts.py`.
- **`.htaccess` handling** (`core/htaccess.py`) parses redirects and exposes `get_missing_routes()`; the pipeline counts `unresolved` routes into final stats. Link-related changes should be checked against `tests/test_htaccess.py` and `tests/test_refs_anchor_links.py`.
- **Tests run modules in isolation** using typed fake-loaders. When adding a step, follow the existing pattern (one `test_<step>.py` per module) rather than wiring a full pipeline test.

## Working rules (from AGENTS.md / GEMINI.md)

- Prefer minimal local fixes over broad refactors; keep behavior backward-compatible.
- Don't hardcode project-specific domains/paths in core logic — drive everything from `config.yaml` and `ProjectContext`.
- Don't commit artifacts from `_workdir/` or `logs/` (already gitignored, but don't `git add -A` these).
- Don't commit unless the user explicitly asks.
- When behavior changes, update tests in the same change.

## Memory pointers

The user maintains an auto-memory at `/Users/roman/.claude/projects/-Users-roman-PycharmProjects-deTilda/memory/` (always loaded via `MEMORY.md`). Read it for ongoing task context — current entries describe per-session plans (e.g., the assets-deletion-vs-rename refactor, adding a local-path "tilda" remnant scan to `checker.py`).
