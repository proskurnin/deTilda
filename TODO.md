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
