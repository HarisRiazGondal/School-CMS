# Next Actions

1. Add secure login/logout and password-reset flows using Django sessions/CSRF, account deactivation behavior, and production secret/cookie guidance; add tests.
2. Add object-level authorization helpers/tests for active school memberships, default deny, cross-school object access, and role scope.
3. Reconcile SchoolClass/Section terminology with the planned Grade/SectionOffering model and decide campus assignment rules before dependent modules.
4. Add people/enrollments with immutable student ID, contextual roll number, historical enrollment, and promotion preview/commit tests.
5. Add domain-specific audit events and update the role-scoped portal boundary before attendance/learning work.
6. Update all impacted memory files and regenerate PROJECT_STATUS.html after each increment.

Verified prerequisite already complete: check, migration-drift check, migrate, and 4-test suite pass from a clean clone.
