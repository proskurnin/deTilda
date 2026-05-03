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

- Доработать веб-форму:
  - Добавить поле Google Analytics Measurement ID, для того чтобы скрипт устанавливался на страницу верно;
  - verify `https://detilda.com/health` and `https://detilda.ru/health` after the GitHub Actions deploy.
- Consider adding deeper Tilda-export validation after the first required-file gate:
  - detect `data-aida-export="yes"` / `data-tilda-project-id` markers in HTML;
  - require at least one HTML page;
  - check that asset folders referenced by HTML exist;
  - report validation details in the processing-result modal.
- Add an automated smoke check for processed zero-block forms that catches invalid `aida-zero-forms-1.0.min.js` before archive delivery.
- Add a deploy smoke check that records the expected version and compares it against `/health`.
- Add browser-console smoke tests for generated archives once Playwright can run reliably in the local/CI environment.
- Реализовать ролевую модель. 
  - Пользователи, которые пользуются платформой должны обязательно регистрироваться. 
  - У пользователя должен быть личный кабинет. Там пользователь видит только свои задачи. 
