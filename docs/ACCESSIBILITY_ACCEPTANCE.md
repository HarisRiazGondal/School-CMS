# Accessibility acceptance

## Local changes and evidence

The shared page shell provides a keyboard-visible skip link to the focusable main landmark, a named account navigation landmark, and a visible `:focus-visible` outline. Django message notifications use a polite live region. Applicable portal forms show a linked, announced error summary when validation fails, keep field-level errors, and use visible labels. The batch promotion and attendance entry tables label row and column headers and connect each interactive control to its student. Other data tables use explicit column scopes.

On 2026-10-15, the following local checks passed:

- `DJANGO_DEBUG=true python manage.py test tests.test_accessibility -v 1` — 4 semantic/HTTP tests passed, including skip/main landmarks, labeled student/oversight/finance/attendance controls, table header scope, and an invalid registration response with an error-summary link.
- `DJANGO_DEBUG=true python manage.py test tests.test_accessibility tests.test_assessment_http tests.test_finance_http tests.test_learning tests.test_oversight_views tests.test_students -v 1` — 45 tests passed. This also exercises rendering and form submissions across the affected portal areas.
- `git diff --check` — passed.
- A local Playwright, Selenium, axe, or browser executable was not available in the workspace, so no browser-driven keyboard audit or automated accessibility scan is claimed.

## Hosted acceptance gate

Production milestone 8 stays open until a human tester verifies the deployed configuration. Record the deployment/build and the exact browser, operating system, assistive technology, and viewport used. Test at least the school administrator, registrar, teacher, student, and finance journeys, including:

1. Use only the keyboard to reach the skip link, navigation, forms, table actions, and confirmation controls. Confirm focus remains visible and the skip link moves focus to the main content.
2. Submit representative invalid forms in admissions/student registration, attendance correction, assignment/assessment, finance, and oversight settings. Confirm the error summary is announced, each summary link reaches its field, and field errors are understandable without relying on color.
3. Navigate roster, attendance, assessment, admissions, and finance tables with a screen reader. Confirm captions/context and row/column relationships make each value and action understandable.
4. Check text and control contrast, browser zoom/reflow, mobile-width overflow, and any uploaded logo/branding configuration used by the school.
5. Record issues and retest fixes. Automated scans may help find defects, but they do not establish conformance or replace this hosted human review.
