from django.contrib import admin
from .models import SchoolClass, Section, Subject, Term

@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "sort_order", "is_active")
    list_filter = ("school", "is_active")
    search_fields = ("name",)

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "school_class", "academic_year")
    list_filter = ("academic_year", "school_class")

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "school", "is_active")
    list_filter = ("school", "is_active")
    search_fields = ("code", "name")

admin.site.register(Term)
