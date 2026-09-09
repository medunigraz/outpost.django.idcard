"""
Django admin configuration for idcard
"""
from django.contrib import admin
from .models import EmployeeCard


@admin.register(EmployeeCard)
class EmployeeCardAdmin(admin.ModelAdmin):
    """Admin interface for EmployeeCard"""
    list_display = (
        'employee_id',
        'full_name',
        'email',
        'organizational_unit_short',
        'has_photo',
        'has_apple_pass',
        'has_google_pass',
        'created_at',
    )
    search_fields = ('employee_id', 'first_name', 'last_name', 'email', 'organizational_unit')
    list_filter = (
        'created_at',
        'organizational_unit_short',
        ('apple_pass_serial', admin.EmptyFieldListFilter),
        ('google_pass_id', admin.EmptyFieldListFilter),
    )
    readonly_fields = ('created_at', 'updated_at', 'apple_pass_serial', 'google_pass_id')
    
    fieldsets = (
        ('Employee Information', {
            'fields': ('employee_id', 'first_name', 'last_name', 'email', 'organizational_unit')
        }),
        ('Photo & QR Code', {
            'fields': ('photo', 'visitenkarte_url')
        }),
        ('Pass Metadata', {
            'fields': ('apple_pass_serial', 'google_pass_id'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def full_name(self, obj):
        """Display full name in list view"""
        return obj.full_name
    full_name.short_description = 'Name'
    
    def has_photo(self, obj):
        """Indicate if employee has a photo"""
        return bool(obj.photo)
    has_photo.boolean = True
    has_photo.short_description = 'Photo'

    # A row exists as soon as someone opens the page, so it does not mean a
    # pass was issued. These two do: the ids are set when a pass is generated.
    def has_apple_pass(self, obj):
        return bool(obj.apple_pass_serial)
    has_apple_pass.boolean = True
    has_apple_pass.short_description = 'Apple'

    def has_google_pass(self, obj):
        return bool(obj.google_pass_id)
    has_google_pass.boolean = True
    has_google_pass.short_description = 'Google'