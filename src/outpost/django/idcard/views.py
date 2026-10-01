"""
Staff-facing views, plus the shared owner-or-staff access check.

The self-service employee flow lives in sso_views.py.
"""
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse, Http404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from outpost.django.campusonline.models import Person
from .models import EmployeeCard
import logging
import qrcode
from io import BytesIO

logger = logging.getLogger(__name__)


@staff_member_required
def employee_list(request):
    employees = EmployeeCard.objects.select_related('person')
    return render(request, 'idcard/employee_list.html', {
        'employees': employees
    })


@staff_member_required
def employee_detail(request, employee_id):
    employee = get_object_or_404(EmployeeCard, person_id=employee_id)
    return render(request, 'idcard/employee_detail.html', {
        'employee': employee
    })


@staff_member_required
def employee_card_json(request, employee_id):
    employee = get_object_or_404(EmployeeCard, person_id=employee_id)
    
    person = employee.person
    photo_url = (
        reverse('campusonline:avatar-private', kwargs={'hash': person.hash})
        if person.hash else None
    )
    data = {
        'employee_id': employee.person_id,
        'full_name': employee.full_name,
        'first_name': person.first_name,
        'last_name': person.last_name,
        'email': person.email,
        'organizational_unit': employee.organization_name,
        'visitenkarte_url': person.card,
        'photo_url': photo_url,
        'created_at': employee.created_at.isoformat(),
        'updated_at': employee.updated_at.isoformat(),
    }
    
    return JsonResponse(data)


@staff_member_required
def generate_qr_code(request, employee_id):
    employee = get_object_or_404(EmployeeCard, person_id=employee_id)
    
    if not employee.person.card:
        return HttpResponse("No Visitenkarte URL configured", status=400)
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(employee.person.card)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    return HttpResponse(buffer.getvalue(), content_type='image/png')


@staff_member_required
def generate_apple_pass(request, employee_id):
    from .apple_pass import apple_pass_download
    return apple_pass_download(request, employee_id)


@staff_member_required
def apple_pass_preview(request, employee_id):
    employee = get_object_or_404(EmployeeCard, person_id=employee_id)
    return render(request, 'idcard/apple_pass_preview.html', {
        'employee': employee
    })


@login_required
def generate_google_pass(request, employee_id):
    """Redirect an employee to their Google Wallet save link.

    Not staff-only: the my-pass button sends employees here for their own card.
    """
    _require_owner_or_staff(request, employee_id)
    from .google_pass import google_pass_download
    return google_pass_download(request, employee_id)


def _require_owner_or_staff(request, employee_id):
    """Raise Http404 unless the requester owns this card, or is staff.

    404 rather than 403 so a probe can't confirm that an id exists.
    """
    if request.user.is_staff:
        return
    if not Person.objects.filter(id=employee_id, username=request.user.username).exists():
        raise Http404
