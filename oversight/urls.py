from django.urls import path

from . import views

app_name = "oversight"
urlpatterns = [
    path("", views.oversight_home, name="home"),
    path("schools/<slug:school_slug>/", views.school_dashboard, name="dashboard"),
    path("schools/<slug:school_slug>/settings/", views.school_settings, name="settings"),
    path("schools/<slug:school_slug>/timetable/new/", views.timetable_create, name="timetable-create"),
    path("schools/<slug:school_slug>/notices/", views.notices, name="notices"),
    path("schools/<slug:school_slug>/notices/new/", views.notice_create, name="notice-create"),
    path("schools/<slug:school_slug>/notices/<int:notice_id>/edit/", views.notice_edit, name="notice-edit"),
]
