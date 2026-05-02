# TODO

This file is the canonical place for future plans and follow-up work.

## Active Rules

- After every version bump and deploy, verify `https://detilda.proskurnin.com/health`.
- Do not consider a bump/deploy task complete until `/health` shows the new version.
- For form/runtime changes, verify runtime behavior and browser console errors, not only HTML.
- Keep plans here when work is deferred beyond the current turn.

## Planned Work

- Add an automated smoke check for processed zero-block forms that catches invalid `aida-zero-forms-1.0.min.js` before archive delivery.
- Add a deploy smoke check that records the expected version and compares it against `/health`.
- Add browser-console smoke tests for generated archives once Playwright can run reliably in the local/CI environment.
