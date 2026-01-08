"""
Django admin configuration for idcard
"""
from django.contrib import admin
from .models import EmployeeCard


@admin.register(EmployeeCard)
class EmployeeCardAdmin(admin.ModelAdmin):
    """Admin interface for EmployeeCard"""
    list_display = ('employee_id', 'first_name', 'last_name', 'created_at')
    search_fields = ('employee_id', 'first_name', 'last_name')
    list_filter = ('created_at',)
