# Browser acceptance smoke

The browser smoke exercises a disposable, synthetic School-CMS instance. It
creates a temporary SQLite database and a Django server bound to an ephemeral
`127.0.0.1` port, seeds five synthetic role accounts, runs the checks, then
terminates the server and deletes the database. It does not accept an external
base URL or target a deployment. Browser logs suppress server output; the test
does not save screenshots, traces, videos, storage state, or credentials. The
runner overrides database, secret-key, proxy, scanner, MFA, and email settings
for its isolated debug server, so inherited deployment configuration cannot
send mail or point the smoke at production data.

Install the separately pinned browser dependencies and run:

```sh
python -m pip install -r requirements.txt -r requirements-e2e.txt
python -m playwright install --with-deps chromium
npm ci --prefix tests/e2e
python scripts/browser_acceptance.py
```

The script checks CSRF rejection for login and logout, then performs a real
CSRF-protected login and logout for school administrator, registrar, teacher,
student, and accountant. Each account opens a role-appropriate portal page and
is denied access to a different school scope with HTTP 403. It also checks the
visible keyboard skip link, focus transfer to the main landmark, keyboard focus
outline, account navigation name, and accessible names for interactive
controls. Uncaught page errors and unexpected console errors fail the run. The
console handler suppresses only Chromium's generic failed-resource 403 message
when its reported resource path exactly matches the exercised login, logout, or
unassigned-school scope endpoint; other console errors remain failures.

The pinned axe-core 4.14.0 scan runs on all five role portal pages for WCAG 2.1
A/AA rules. The npm lockfile records the
exact package and integrity hash. To exercise only browser behavior where npm
is unavailable, pass `--skip-axe`; that run does not claim an automated
accessibility scan.

The runner serves the pinned local axe bytes through a Playwright route at a
same-origin synthetic URL, then loads that URL as a script. This respects the
application's `script-src 'self'` Content Security Policy; it does not disable
CSP or insert inline script code.

Package choices follow the upstream [Playwright Python installation and
browser-version guidance](https://playwright.dev/python/docs/intro) and the
[axe-core 4.14.0 release](https://github.com/dequelabs/axe-core/releases).
Reinstall Chromium after changing the Playwright pin because Playwright
requires its matching browser build.

## Acceptance status

This is a reproducible synthetic smoke, not the hosted human acceptance gate.
The local environment has no browser executable. Installing Playwright 1.63.0
succeeded, but its supported Chromium download repeatedly returned a corrupt
0 MiB archive (`End of central directory record signature not found`). The
acceptance script therefore has **not** been represented as browser-run. The
existing Django semantic accessibility tests remain separate evidence. A CI
runner with the pinned Playwright browser must run this smoke; a human must
still complete the deployed five-role, keyboard, assistive-technology, zoom,
contrast, and responsive review described in
[`ACCESSIBILITY_ACCEPTANCE.md`](ACCESSIBILITY_ACCEPTANCE.md). Neither automated
axe results nor synthetic browser coverage establish the hosted human review or
100% acceptance.
