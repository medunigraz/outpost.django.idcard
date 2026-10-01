"""
SSO Integration for Employee ID Card Generation

Integrates with outpost.django.campusonline for employee data.
"""
import base64
import io
import logging
import re

import qrcode
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.urls import reverse
from django.utils import translation
from django.views.decorators.vary import vary_on_headers
from outpost.django.campusonline.models import Person
from .models import EmployeeCard
from .apple_pass import apple_pass_download

logger = logging.getLogger(__name__)

_IOS_RE = re.compile(r"iPhone|iPad|iPod", re.IGNORECASE)
_ANDROID_RE = re.compile(r"Android", re.IGNORECASE)


def _detect_device(user_agent):
    if not user_agent:
        return "desktop"
    if _IOS_RE.search(user_agent):
        return "ios"
    if _ANDROID_RE.search(user_agent):
        return "android"
    return "desktop"


def _set_language_cookie(response, lang):
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        lang,
        max_age=settings.LANGUAGE_COOKIE_AGE,
        path=settings.LANGUAGE_COOKIE_PATH,
        domain=settings.LANGUAGE_COOKIE_DOMAIN,
        secure=settings.LANGUAGE_COOKIE_SECURE,
        httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
        samesite=settings.LANGUAGE_COOKIE_SAMESITE,
    )


def _qr_data_uri(text, box_size=8):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#007c31", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@login_required
def generate_my_pass(request):
    """Generate and download wallet pass for logged-in user"""
    person = get_object_or_404(Person, username=request.user.username)

    if not person.employed:
        return HttpResponse(
            "<h1>Not Eligible</h1>"
            "<p>Digital ID cards are only available to currently-employed staff.</p>",
            status=403,
        )

    EmployeeCard.objects.get_or_create(person=person)

    return apple_pass_download(request, person.id)


@login_required
@vary_on_headers("User-Agent", "Accept-Language")
def my_pass_preview(request):
    """Show preview page before generating pass"""
    lang = request.GET.get("lang")
    if lang in dict(settings.LANGUAGES):
        response = redirect("idcard:my_pass_preview")
        _set_language_cookie(response, lang)
        return response

    # Outpost has no LocaleMiddleware, so scope the language to this request.
    with translation.override(translation.get_language_from_request(request)):
        try:
            person = Person.objects.get(username=request.user.username)
        except Person.DoesNotExist:
            return render(request, 'idcard/error.html', {
                'error_title': 'Person Not Found',
                'error_message': f'No CAMPUSonline person record found for username: {request.user.username}',
            })

        if not person.employed:
            return render(request, 'idcard/error.html', {
                'error_title': 'Not Eligible',
                'error_message': 'Digital ID cards are only available to currently-employed staff.',
            })

        employee_card, _ = EmployeeCard.objects.get_or_create(person=person)

        device = _detect_device(request.META.get("HTTP_USER_AGENT", ""))
        page_url = request.build_absolute_uri(reverse("idcard:my_pass_preview"))
        qr_data_uri = _qr_data_uri(page_url) if device == "desktop" else None

        return render(request, 'idcard/my_pass_preview.html', {
            'employee_card': employee_card,
            'person': person,
            'device': device,
            'qr_data_uri': qr_data_uri,
        })
