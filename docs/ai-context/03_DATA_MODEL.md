# Data Model

## Identity rule

Student is one permanent profile. Enrollment is a student's placement for one academic year. Roll number belongs to that enrollment/section context and is never the primary identity.

## Core entities

School -> Campus, AcademicYear -> Term, Grade -> SectionOffering, Student -> Enrollment, Guardian <-> Student through GuardianStudentRelation, Teacher -> TeacherAssignment, Enrollment -> AttendanceRecord/Invoice, Assessment -> Result/ReportCard, and AuditLog across sensitive changes.

Student uses an immutable UUID primary key and a school-scoped human-facing student_code generated once. Do not put current class, section, year, or roll number on Student.

Enrollment stores student, school, campus, academic_year, section_offering, roll_number, status, dates, outcome, and promotion lineage. Default policy is one enrollment per student/year; unique section_offering + roll_number. Withdrawn/completed rows remain queryable.

PromotionDecision stores source enrollment, optional target enrollment, outcome (promoted, repeated, conditional, graduated, withdrawn, transferred), actor, approval, reason, and batch reference. Promotion creates a new Enrollment and never overwrites source history.

AttendanceRecord is unique per session/enrollment. Posted finance entries are decimal-safe and corrected using adjustment/reversal records. Use protected deletes for students, historical enrollments, finalized marks, and posted payments. Validate that related school/campus/year records agree.

## Required lifecycle tests

Registration creates one permanent code and first enrollment. Promotion preserves the code and old enrollment. Re-admission reuses the student. Duplicate year enrollment and contextual roll numbers are blocked. Attendance duplication is blocked. Corrections and reversals preserve original history.
