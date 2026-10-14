# Roles and Permissions

Default deny. Permissions combine action, resource, scope, and workflow state. Apply them to pages, APIs, querysets, search, dashboards, exports, attachments, and bulk operations.

| Role | Default scope |
|---|---|
| Platform Super Admin | Global configuration and operational health; private student/finance access is explicit, purposeful, and logged |
| School Admin / Principal | Full school/campus operations within delegated authority |
| Admissions / Registrar | Applications, guardians, documents, registration, enrollments, transfers, and student history |
| Teacher | Assigned subject + section + academic year; attendance, assignments, grading, and feedback |
| Student | Own profile, current placement, attendance, learning, published results, notices, and history allowed by policy |
| Accountant / Fee Office | Fee plans, invoices, payments, receipts, concessions, adjustments, and finance reports |

Teacher role never grants school-wide access. Finance scope does not grant private academic access. Guardian access is optional and requires a verified relationship. Deactivated users cannot authenticate; historical attribution remains.

Required authorization tests cover direct-object access, modified IDs, exports, files, aggregates, and cross-school/campus attempts.
