# Roles and Permissions

Default deny. Action permission is combined with active User, active School and active SchoolMembership. Search/list/detail/form choices, services, learning roster and private Admin interfaces enforce scope. Platform superuser status alone grants no student/learning data access; scoped authorized student reads are audited.

| Role | Implemented pilot access | Limit |
|---|---|---|
| Platform Super Admin | Trusted configuration Admin | Private records require explicit active school role and audited access |
| School Admin | School register/history, promotion confirmation, teaching oversight, assessment finalization/publication, scoped report-card selector and finance | No automatic other-school access |
| Registrar | School registration/guardians/history and promotion preview | Cannot confirm promotion |
| Teacher | Assigned attendance/classwork, question-bank authoring, scheduled assessments and manual marking | Cannot finalize/publish; membership alone grants no section |
| Student | Own active enrollment/work/assessment attempts; own published historical transcript and fee statements/receipts | Cannot select another enrollment/student or view unpublished grades/keys |
| Accountant | School fee plans, invoices, payments/receipts, reasoned reversals and currency-separated balances | No grading/student academic-record authority |
| Guardian | Contact relation only | Guardian portal is not implemented |

Login uses username and Django session cookies. Account deactivation flushes stored session identity. Password reset responses avoid account enumeration; inactive accounts receive no reset mail. POST logout and mutating forms require CSRF tokens.

The implementation does not yet include a configurable granular permission-template editor, campus-restricted staff memberships, public login throttling or MFA. Campus data consistency is enforced, but staff authority currently spans their authorized school/explicit teacher assignments. Do not claim campus-level staff restriction is implemented.

Assessment attempts are scoped to active enrollment while in progress; published transcript reads retain old enrollments. Finance reads retain historical enrollment context and require active school-role ownership. Cross-school roles, teacher finance requests, non-admin publication, withdrawn/revoked attempt access and malformed admin report selectors are covered by tests. Sensitive financial and transcript reads record metadata audit events.
