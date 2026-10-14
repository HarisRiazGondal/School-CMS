# Roles and Permissions

Default deny. Action permission is combined with active User, active School and active SchoolMembership. Search/list/detail/form choices, services, learning roster and private Admin interfaces enforce scope. Platform superuser status alone grants no student/learning data access; scoped authorized student reads are audited.

| Role | Implemented pilot access | Limit |
|---|---|---|
| Platform Super Admin | Trusted configuration Admin | Private records require explicit active school role and audited access |
| School Admin | School register/history, promotion confirmation, attendance oversight and permitted grading | No automatic other-school access |
| Registrar | School registration/guardians/history and promotion preview | Cannot confirm promotion |
| Teacher | Assigned subject/section/year attendance, publishing and grading | Membership alone cannot grant section access |
| Student | Own active enrollment, eligible published work, own responses and feedback | Cannot select another enrollment or read another submission |
| Accountant | Membership schema and home only | Finance workflow is not implemented |
| Guardian | Contact relation only | Guardian portal is not implemented |

Login uses username and Django session cookies. Account deactivation flushes stored session identity. Password reset responses avoid account enumeration; inactive accounts receive no reset mail. POST logout and mutating forms require CSRF tokens.

The implementation does not yet include a configurable granular permission-template editor, campus-restricted staff memberships, public login throttling or MFA. Campus data consistency is enforced, but staff authority currently spans their authorized school/explicit teacher assignments. Do not claim campus-level staff restriction is implemented.
