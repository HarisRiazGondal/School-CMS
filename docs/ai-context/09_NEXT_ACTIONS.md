# Next Actions

1. Run the Django foundation in a clean environment: install requirements, copy .env.example, run python manage.py check, generate migrations, run migrate, and run the tests. Record actual output.
2. Add explicit authorization helpers/tests for active school memberships, default deny, cross-school object access, and role scope.
3. Review security defaults for production cookies, CSRF, password reset, account deactivation, and admin access.
4. Add people/enrollments with immutable student ID, contextual roll number, historical enrollment, and promotion preview/commit tests.
5. Add domain-specific audit events and update the role-scoped portal boundary before attendance/learning work.
6. Update all impacted memory files and regenerate PROJECT_STATUS.html after each increment.

Prerequisite: resolve only policy choices that block a safe schema; document defaults for the rest.
