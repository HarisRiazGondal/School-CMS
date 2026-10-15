from django.urls import path
from . import views

app_name = "privatefiles"
urlpatterns = [
    path("my-files/", views.my_files, name="my-files"),
    path("assignments/<int:assignment_id>/upload/", views.assignment_upload, name="assignment-upload"),
    path("submissions/<int:submission_id>/upload/", views.submission_upload, name="submission-upload"),
    path("<uuid:attachment_id>/download/", views.download, name="download"),
]
