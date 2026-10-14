# Next Actions

1. Run the Django foundation in a clean environment: install requirements, copy .env.example, run python manage.py check, and record actual output.
2. Add accounts with a custom User, school-scoped memberships, roles, account deactivation, and secure session/password-reset baseline.
3. Add schools and academics models with constraints for school/campus/year/grade/section/subject; create migrations and admin registrations.
4. Add model/service authorization tests, especially cross-scope access and default-deny behavior.
5. Add people/enrollments with immutable student ID, contextual roll number, historical enrollment, and promotion preview/commit tests.
6. Update all impacted memory files and regenerate PROJECT_STATUS.html after each increment.

Prerequisite: resolve only policy choices that block a safe schema; document defaults for the rest.
