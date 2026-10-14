from django.contrib import admin
from .models import AcademicYear, Campus, School

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    search_fields = ("name", "slug")

@admin.register(Campus)
class CampusAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "school", "is_active")
    list_filter = ("school", "is_active")
    search_fields = ("name", "code")

@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "starts_on", "ends_on", "is_active")
    list_filter = ("school", "is_active")
