from django.urls import path

from . import views

app_name = "assessment"
urlpatterns = [
    path("", views.assessment_home, name="home"),
    path("questions/new/", views.question_create, name="question-create"),
    path("new/", views.assessment_create, name="create"),
    path("<int:assessment_id>/", views.assessment_detail, name="detail"),
    path("<int:assessment_id>/attach/", views.attach_questions, name="attach"),
    path("<int:assessment_id>/open/", views.assessment_open, name="open"),
    path("<int:assessment_id>/start/", views.assessment_start, name="start"),
    path("attempts/<int:attempt_id>/", views.attempt_detail, name="attempt"),
    path("attempts/<int:attempt_id>/save/", views.attempt_save, name="save"),
    path("attempts/<int:attempt_id>/submit/", views.attempt_submit, name="submit"),
    path("answers/<int:answer_id>/mark/", views.answer_mark, name="mark"),
    path("attempts/<int:attempt_id>/finalize/", views.attempt_finalize, name="finalize"),
    path("attempts/<int:attempt_id>/publish/", views.attempt_publish, name="publish"),
    path("report-card/", views.report_card, name="report-card"),
]
