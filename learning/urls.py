from django.urls import path

from . import views

app_name = "learning"

urlpatterns = [
    path("", views.learning_home, name="home"),
    path("sections/<int:section_id>/attendance/", views.attendance_list, name="attendance-list"),
    path("sections/<int:section_id>/attendance/record/", views.attendance_entry, name="attendance-entry"),
    path("attendance/history/", views.student_attendance_history, name="student-attendance-history"),
    path("attendance/corrections/", views.attendance_correction_queue, name="attendance-correction-queue"),
    path("attendance/corrections/<int:correction_id>/review/", views.attendance_correction_review, name="attendance-correction-review"),
    path("attendance/records/<int:record_id>/correct/", views.attendance_correction_request, name="attendance-correction-request"),
    path("assignments/new/", views.assignment_create, name="assignment-create"),
    path("assignments/<int:assignment_id>/", views.assignment_detail, name="assignment-detail"),
    path("assignments/<int:assignment_id>/submit/", views.assignment_submit, name="assignment-submit"),
    path("submissions/<int:submission_id>/grade/", views.submission_grade, name="submission-grade"),
]
