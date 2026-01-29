"""
Views for Digital ID Cards with Google Wallet support
"""
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from .models import EmployeeCard
import qrcode
from io import BytesIO


@login_required
def employee_list(request):
    """List all employees with ID cards"""
    employees = EmployeeCard.objects.all()
    return render(request, 'idcard/employee_list.html', {
        'employees': employees
    })


@login_required
def employee_detail(request, employee_id):
    """View details for a specific employee ID card"""
    employee = get_object_or_404(EmployeeCard, employee_id=employee_id)
    return render(request, 'idcard/employee_detail.html', {
        'employee': employee
    })


@login_required
def employee_card_json(request, employee_id):
    """Return employee card data as JSON (for API access)"""
    employee = get_object_or_404(EmployeeCard, employee_id=employee_id)
    
    data = {
        'employee_id': employee.employee_id,
        'full_name': employee.full_name,
        'first_name': employee.first_name,
        'last_name': employee.last_name,
        'email': employee.email,
        'organizational_unit': employee.organizational_unit,
        'visitenkarte_url': employee.visitenkarte_url,
        'photo_url': employee.photo.url if employee.photo else None,
        'created_at': employee.created_at.isoformat(),
        'updated_at': employee.updated_at.isoformat(),
    }
    
    return JsonResponse(data)


def generate_qr_code(request, employee_id):
    """Generate QR code for employee's Visitenkarte URL"""
    employee = get_object_or_404(EmployeeCard, employee_id=employee_id)
    
    if not employee.visitenkarte_url:
        return HttpResponse("No Visitenkarte URL configured", status=400)
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(employee.visitenkarte_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    return HttpResponse(buffer.getvalue(), content_type='image/png')


@login_required
def generate_apple_pass(request, employee_id):
    """Generate Apple Wallet pass for employee"""
    from .apple_pass import apple_pass_download
    return apple_pass_download(request, employee_id)


@login_required
def apple_pass_preview(request, employee_id):
    """Preview page before downloading Apple Wallet pass"""
    employee = get_object_or_404(EmployeeCard, employee_id=employee_id)
    return render(request, 'idcard/apple_pass_preview.html', {
        'employee': employee
    })


@login_required
def generate_google_pass(request, employee_id):
    """Generate Google Wallet pass for employee"""
    from .google_pass import google_pass_download
    return google_pass_download(request, employee_id)