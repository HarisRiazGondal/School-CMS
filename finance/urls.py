from django.urls import path

from . import views

app_name = "finance"
urlpatterns = [
    path("", views.finance_home, name="home"),
    path("schools/<slug:school_slug>/", views.school_home, name="school-home"),
    path("schools/<slug:school_slug>/plans/new/", views.fee_plan_create, name="plan-create"),
    path("schools/<slug:school_slug>/invoices/new/", views.invoice_issue, name="invoice-issue"),
    path("invoices/<uuid:invoice_id>/", views.invoice_detail, name="invoice-detail"),
    path("invoices/<uuid:invoice_id>/payments/new/", views.payment_post, name="payment-post"),
    path("payments/<uuid:payment_id>/reverse/", views.payment_reverse, name="payment-reverse"),
    path("statement/", views.student_statement, name="student-statement"),
    path("receipts/<uuid:receipt_id>/", views.receipt_detail, name="receipt-detail"),
]
