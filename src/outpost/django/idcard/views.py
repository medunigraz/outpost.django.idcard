"""
Views for Digital ID Cards with Google Wallet support
"""
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse, Http404
from django.contrib.auth.decorators import login_required
from .models import EmployeeCard
import logging
import qrcode
from io import BytesIO

logger = logging.getLogger(__name__)


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


@login_required
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


def _requester_employee_id(request):
    """EmployeeCard.employee_id belonging to the logged-in user, or None.

    Person is the only link from a Django user to an EmployeeCard, so this
    mirrors the lookup sso_views does. Imported lazily because the sandbox
    harness runs without outpost.django.campusonline installed.
    """
    try:
        from outpost.django.campusonline.models import Person
    except ImportError:
        return None

    username = request.user.username
    if not username:
        return None
    try:
        return Person.objects.get(username=username).id
    except Person.DoesNotExist:
        return None


@login_required
def employee_photo(request, employee_id):
    """Serve an employee's ID photo to that employee, or to staff.

    Templates must never link a photo via MEDIA_URL: /media/ is served with
    no authentication whatsoever, so `employee.photo.url` hands out a
    permanently fetchable link to an internal-only portrait. That is the same
    leak `avatar_private` exists to prevent.
    """
    employee = get_object_or_404(EmployeeCard, employee_id=employee_id)

    if not request.user.is_staff:
        if _requester_employee_id(request) != employee.employee_id:
            raise Http404

    if not employee.photo:
        raise Http404

    try:
        with employee.photo.open('rb') as fh:
            data = fh.read()
    except (OSError, ValueError) as e:
        logger.error(f"Could not read stored photo for employee {employee_id}: {e}")
        raise Http404

    response = HttpResponse(data, content_type='image/jpeg')
    # Personal data: reusable by this browser, never by a shared cache.
    response['Cache-Control'] = 'private, max-age=300'
    return response
