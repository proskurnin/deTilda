# TODO

This file is the canonical place for future plans and follow-up work.

## Active Rules

- After every version bump and deploy, verify `https://detilda.proskurnin.com/health`.
- Do not consider a bump/deploy task complete until `/health` shows the new version.
- After every production deploy, verify both `https://detilda.com/health` and `https://detilda.ru/health`.
- Do not consider a production deploy complete until both production `/health` endpoints show the expected version.
- For form/runtime changes, verify runtime behavior and browser console errors, not only HTML.
- Keep plans here when work is deferred beyond the current turn.

## Planned Work

### Post-5.7.6 verification and diagnostics context

Context:

- Current deployed version: `5.7.6`.
- `main`: `60948cf Release 5.7.6`.
- `prod`: `ef73e8b Merge branch 'main' into prod`.
- Tag: `v5.7.6`.
- Stage `/health`: `https://detilda.proskurnin.com/health` returned `5.7.6`.
- Production `/health`: `https://detilda.com/health` and `https://detilda.ru/health` returned `5.7.6`.
- Release `5.7.6` was a technical patch redeploy: only `manifest.json` and
  `CHANGELOG.md` changed.
- Local verification before deploy: `python -m pytest tests/ -q` returned
  `346 passed, 2 warnings` on both `main` and merged `prod`.
- Stage workflow: `29537409100` passed.
- Production workflow: `29538320332` passed; it was started manually with
  `workflow_dispatch` because the `prod` push workflow did not appear in
  `gh run list`.

Next plan:

1. Verify the real public Stage flow for “Мои задачи”:
   - upload one ZIP;
   - upload several ZIP files;
   - open `детали`;
   - download `отчёт`;
   - confirm failed jobs show a clear error reason, not only `ошибка`.
2. Re-run the problem archive `input/raizel.ltd.zip` on fresh `5.7.6`:
   - confirm whether `zero-block` runtime smoke-check passes;
   - if it fails, collect the exact error from job details and
     `processing_report.json`;
   - use the report to localize the failing runtime file, form block, or
     cleaner/smoke-check step.
3. If `raizel.ltd.zip` still fails:
   - identify the exact module and pipeline step involved;
   - prefer a minimal fix in the relevant runtime/script cleaner/smoke-check
     module;
   - add a focused regression test.
4. Re-check multi-file upload UX:
   - shared email/GA mode;
   - per-file email/GA mode;
   - `[info@]` helper deriving `info@<domain>` from the ZIP filename without
     `.zip`;
   - public API/UI tests for any missed behavior.
5. After fixes, ship the next patch release:
   - update `CHANGELOG.md`;
   - run `python -m pytest tests/ -q`;
   - bump patch via `python tools/bump_version.py patch`;
   - commit, tag, push `main`;
   - verify Stage workflow and `/health`;
   - merge to `prod`, verify production workflow and both production
     `/health` endpoints.
