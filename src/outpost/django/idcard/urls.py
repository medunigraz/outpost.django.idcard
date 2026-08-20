"""
URL patterns for Digital ID Cards with SSO integration
"""
from django.urls import path
from . import views
from . import sso_views

app_name = 'idcard'

urlpatterns = [
    # Employee list and detail views (admin use)
    path('', views.employee_list, name='employee_list'),
    path('employee/<int:employee_id>/', views.employee_detail, name='employee_detail'),
    
    # API endpoints
    path('api/employee/<int:employee_id>/', views.employee_card_json, name='employee_json'),
    
    # QR code generation
    path('qr/<int:employee_id>/', views.generate_qr_code, name='generate_qr'),
    
    # Wallet pass generation (admin/manual)
    path('apple-pass/<int:employee_id>/', views.generate_apple_pass, name='apple_pass'),
    path('apple-pass-preview/<int:employee_id>/', views.apple_pass_preview, name='apple_pass_preview'),
    path('google-pass/<int:employee_id>/', views.generate_google_pass, name='google_pass'),
    
    # SSO-based auto-generation (for end users)
    path('my-pass/', sso_views.my_pass_preview, name='my_pass_preview'),
    path('my-pass/generate/', sso_views.generate_my_pass, name='generate_my_pass'),
    path('my-pass/photo/', sso_views.my_pass_photo, name='my_pass_photo'),
]