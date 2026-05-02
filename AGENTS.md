# AGENTS.md — deTilda

This file is the single source of truth for all AI coding agents working in this repository.

All agents must read and follow this file before making changes, including:

- Codex
- Claude Code
- Gemini CLI
- Cursor
- Copilot
- any other AI coding assistant

Do not duplicate or override these rules in `CLAUDE.md`, `GEMINI.md`, or other agent-specific files.

If another instruction file exists, it must only point back to this file.

If there is any conflict between instruction files, `AGENTS.md` wins.

---

## Purpose

deTilda converts a Tilda ZIP export into a self-hostable site via a deterministic multi-step pipeline.

Primary goals:

- no unnecessary Tilda dependencies in the final site;
- stable links and assets;
- reproducible output;
- clear logs and reports;
- offline-first processing where possible.

---

## Project Context

- Entry point: `main.py`.
- Main orchestration: `core/pipeline.py`.
- The actual pipeline order is defined in `core/pipeline.py`.
- Pipeline order is part of the project contract. Reordering steps is a breaking behavioral change.
- Global config/rules: `config/config.yaml`.
- Typed config loading: `core/config_loader.py` and `core/schemas.py`.
- Pydantic compatibility layer: `core/pydantic_compat.py`.
- Version source of truth: `manifest.json`.
- Runtime templates copied into processed sites: `resources/`.
- Runtime script handling: `core/runtime_scripts.py`, `core/script_cleaner.py`.
- Future plans and deferred work: `TODO.md`.
- Change history: `CHANGELOG.md`.
- Generated projects and temporary files usually live in `_workdir/`.
- Transient logs live in `logs/`.

The README, `CLAUDE.md`, `GEMINI.md`, and other documentation may become outdated. Always check `core/pipeline.py` for the current real pipeline order.

---

## Commands

Run the tool:

```bash
python main.py
```

Run all tests:

```bash
python -m pytest tests/ -q
```

Run one test file:

```bash
python -m pytest tests/test_refs_main.py -q
```

Run one test:

```bash
python -m pytest tests/test_refs_main.py::test_name -q
```

Bump version:

```bash
python tools/bump_version.py {patch|minor|major}
```

CI runs tests from `.github/workflows/tests.yml`.

---

## Core Engineering Principles

- Prefer minimal, local fixes over broad refactors.
- Do not refactor without a direct request.
- Do not change project architecture without approval.
- Preserve pipeline order semantics.
- Keep processing offline-first and deterministic where possible.
- Preserve backward compatibility for existing exports and tests.
- Do not remove existing logic unless it is proven to be unnecessary.
- Avoid heavy dependencies.
- Do not add real `pydantic` as a dependency. Use `core/pydantic_compat.py`.
- Do not hardcode project-specific domains or paths in core logic.
- Keep logs and reports informative.
- Do not silently swallow critical processing errors.
- Do not commit unless the user explicitly asks.
- Record deferred plans in `TODO.md`.
- Record completed user-visible or operational changes in `CHANGELOG.md`.

---

## Required Working Method

Before changing code:

1. Find the factual cause of the problem.
2. Confirm the cause using specific files, code paths, logs, or tests.
3. Separate facts, hypotheses, and checks.
4. Prefer a minimal safe patch.
5. Avoid rewriting whole files when a targeted change is enough.

For bug fixes:

1. Reproduce or localize the issue first.
2. Identify the exact module and pipeline step involved.
3. Check neighboring step modules for cross-step side effects.
4. Apply the smallest safe fix.
5. Run relevant tests.
6. Verify that old behavior was not broken.

Do not present assumptions as facts.

---

## Architecture Notes

### `ProjectContext`

`ProjectContext` in `core/project.py` is the per-run object passed through pipeline steps.

It bundles:

- `project_root`;
- typed `config_loader`;
- shared `rename_map`.

New step code should use `ProjectContext`, not raw disconnected paths.

---

### `rename_map`

`rename_map` is built during asset processing and consumed by later steps such as refs and cleaners.

Rules:

- anything renaming files must update `rename_map`;
- anything rewriting links must read `rename_map`;
- broken-link regressions often come from skipping this rule.

---

### `config/config.yaml`

`config/config.yaml` is the main source of processing rules, including:

- regex patterns;
- replacement rules;
- file extensions;
- deletion lists;
- service-file copy rules;
- Tilda cleanup behavior.

New config fields require updates in:

- `core/schemas.py`;
- `core/config_loader.py`;
- defaults/docs where applicable;
- tests.

---

### `manifest.json`

`manifest.json` is the source of truth for:

- `version`;
- `release_date`;
- `paths.*`;
- `build.package_name`.

Do not hardcode versions elsewhere.

Use:

```bash
python tools/bump_version.py {patch|minor|major}
```

when version metadata must be changed.

After every version bump and deploy, verify the deployed version through:

```bash
curl -fsS https://detilda.proskurnin.com/health
```

Do not consider a bump/deploy task complete until `/health` shows the new version.

For production deploys, also verify:

```bash
curl -fsS https://detilda.com/health
curl -fsS https://detilda.ru/health
```

Do not consider a production deploy complete until both production `/health` endpoints show the expected version.

---

### Runtime Script Protection

Be very careful with:

- `core/runtime_scripts.py`;
- `core/script_cleaner.py`;
- `tilda-forms-1.0.min.js`;
- pop-up forms;
- form initialization;
- `form-handler.js`;
- `send_email.php`.

The script cleaner may remove Tilda inline scripts, but it must not break required runtime behavior.

Tilda scripts can have side effects beyond network submission. Some scripts may be needed for:

- form rendering;
- pop-up opening;
- pop-up centering;
- field validation;
- input masks;
- UI behavior.

Do not remove Tilda scripts only because their names contain `tilda`.

Before removing or replacing a Tilda script, verify what functionality depends on it.

---

### `.htaccess` Handling

`.htaccess` logic lives in `core/htaccess.py`.

It parses redirects and exposes missing routes via `get_missing_routes()`.

Link-related changes should be checked against:

```bash
python -m pytest tests/test_htaccess.py -q
python -m pytest tests/test_refs_anchor_links.py -q
```

---

## Change Rules

1. If behavior changes, update tests in `tests/` in the same change.
2. If a new pipeline step is added, add focused tests for that step.
3. For new config fields, update schema, loader, defaults/docs, and tests.
4. For path/link logic changes, verify HTML/CSS/JS reference updates.
5. For asset-renaming logic, verify `rename_map`.
6. For Tilda cleanup logic, verify that forms and runtime behavior still work.
7. For `.htaccess` changes, verify redirect and missing-route behavior.
8. Do not commit generated runtime artifacts from `_workdir/`.
9. Do not commit transient logs from `logs/`.
10. Do not use `git add -A` blindly.

---

## deTilda-Specific Rules

- Preserve the offline-first approach.
- The final site should be self-hostable.
- Remove unnecessary Tilda remnants, but do not break required runtime behavior.
- Keep form handling local where the project intentionally replaces Tilda submission.
- Do not allow form submission to Tilda servers when local handling is expected.
- Do not remove Tilda visual/runtime initialization without verification.
- Preserve required `data-*` attributes in HTML.
- Preserve anchors, lazyload images, CSS references, JS references, and `.htaccess` routes.
- Do not hardcode one exported project’s domain/path into generic processing logic.

---

## Validation Checklist

Before finalizing planned or completed work:

- update `TODO.md` when a plan is added, changed, completed, or deferred;
- update `CHANGELOG.md` for completed user-visible or operational changes.

Before finalizing changes, run:

```bash
python -m pytest tests/ -q
```

For form/runtime-related changes, also verify:

- forms are visible;
- form rendering is checked at runtime, not only by inspecting HTML;
- pop-up forms open;
- pop-up forms are centered correctly;
- validation/UI behavior is not broken;
- local form submission still works;
- forms are not submitted to Tilda servers;
- browser console has no new critical errors;
- browser console has no new form/runtime initialization errors;
- required Tilda `data-*` attributes are preserved.

For script cleaner/runtime changes, run relevant tests such as:

```bash
python -m pytest tests/test_script_cleaner_tilda_media.py -q
python -m pytest tests/test_assets_runtime_scripts.py -q
```

For link/reference changes, run relevant tests such as:

```bash
python -m pytest tests/test_refs_main.py -q
python -m pytest tests/test_refs_anchor_links.py -q
python -m pytest tests/test_htaccess.py -q
```

If version changed, verify `manifest.json` consistency:

- `version`;
- `release_date`;
- `build.package_name`.

---

## CLI Agent Guidance

- Prefer small changes with explicit intent.
- Use focused commits only when the user asks to commit.
- Review neighboring modules before changing pipeline behavior.
- Do not invent missing context.
- Do not claim a bug is fixed unless tests or direct checks confirm it.
- Do not hide uncertainty.
- When there are several possible causes, list them as hypotheses and say how to check each one.
- If a task involves logs, archives, or generated output, base conclusions only on factual lines or calculated results.

---

## Response Style

When reporting back to the user:

- Be concise and direct.
- Show the concrete cause.
- Reference specific files, functions, tests, or log lines.
- Do not soften confirmed problems.
- Do not say “maybe” when there is factual confirmation.
- Clearly separate:
  - facts;
  - hypotheses;
  - checks performed;
  - recommended fix.

Preferred structure for bug analysis:

```text
Причина:
...

Факт:
...

Что исправить:
...

Как проверить:
...
```

---

## Agent-Specific Files

`CLAUDE.md`, `GEMINI.md`, and similar files must not contain separate project rules.

They should only redirect agents to this file.

Recommended `CLAUDE.md`:

```md
# Claude Code Instructions

The canonical project instructions are in `AGENTS.md`.

Before making any changes, read and follow `AGENTS.md`.

Do not treat this file as a separate source of project rules.
If there is any conflict, `AGENTS.md` wins.
```

Recommended `GEMINI.md`:

```md
# Gemini Instructions

The canonical project instructions are in `AGENTS.md`.

Before making any changes, read and follow `AGENTS.md`.

Do not treat this file as a separate source of project rules.
If there is any conflict, `AGENTS.md` wins.
```
