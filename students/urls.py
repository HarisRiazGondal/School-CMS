from django.urls import path
from . import views

app_name = "students"
urlpatterns = [
    path("<slug:school_slug>/students/", views.student_list, name="list"),
    path("<slug:school_slug>/students/register/", views.student_register, name="register"),
    path("<slug:school_slug>/students/<str:student_code>/", views.student_detail, name="detail"),
    path("<slug:school_slug>/students/<str:student_code>/years/<str:year_name>/promotion/", views.promotion_preview_view, name="promotion-preview"),
    path("<slug:school_slug>/students/<str:student_code>/years/<str:year_name>/promotion/confirm/", views.promotion_commit_view, name="promotion-confirm"),
]
