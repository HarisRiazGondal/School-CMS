from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import SchoolMembership, User

@admin.register(User)
class UserAdmin(UserAdmin):
    list_display = ("username", "email", "is_active", "is_staff")
    search_fields = ("username", "email")

@admin.register(SchoolMembership)
class SchoolMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "school", "role", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("user__username", "user__email", "school__name")
