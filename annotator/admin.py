from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
	list_display = ("username", "role", "is_staff", "total_annotations", "today_annotations", "last_activity")
	list_filter = ("role", "is_staff", "is_superuser", "is_active")
	search_fields = ("username", "first_name", "last_name", "email")
	fieldsets = BaseUserAdmin.fieldsets + (
		("Annotatsiya statistikasi", {"fields": ("role", "total_annotations", "today_annotations", "last_activity")}),
	)
