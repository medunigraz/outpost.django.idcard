"""
SSO Integration for Employee ID Card Generation

Integrates with outpost.django.campusonline for employee data.
"""
import base64
import io
import logging
import re

import qrcode
import requests
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import translation
from .models import EmployeeCard
from .apple_pass import apple_pass_download

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("de", "en")
DEFAULT_LANGUAGE = "de"

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


def _resolve_language(request):
    lang = request.GET.get("lang")
    if lang in SUPPORTED_LANGUAGES:
        request.session["idcard_lang"] = lang
        return lang
    return request.session.get("idcard_lang", DEFAULT_LANGUAGE)


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

try:
    from outpost.django.campusonline.models import Person
    CAMPUSONLINE_AVAILABLE = True
except ImportError:
    CAMPUSONLINE_AVAILABLE = False
    Person = None


def _localized(value, lang='de'):
    """Resolve an HStoreField multilingual dict to a plain string."""
    if isinstance(value, dict):
        return value.get(lang) or value.get('en') or next(iter(value.values()), '') or ''
    return value or ''


def _title_part(hstore, key):
    """Pick a key out of a {prefix, suffix}-shaped hstore, tolerating None/missing."""
    if isinstance(hstore, dict):
        return hstore.get(key) or ''
    return ''


def _person_to_card_defaults(person):
    """Build the dict of EmployeeCard fields populated from a CAMPUSonline Person."""
    primary_org = person.organizations.first()
    if primary_org:
        org_full = _localized(primary_org.name)
        org_short = primary_org.short or ''
        dienstort = primary_org.address or ''
        org_phone = primary_org.phone or ''
        org_email = primary_org.email or ''
    else:
        org_full = org_short = dienstort = org_phone = org_email = ''

    return {
        'first_name': person.first_name or '',
        'last_name': person.last_name or '',
        'title_prefix': _title_part(person.academic_title, 'prefix'),
        'title_suffix': _title_part(person.academic_title, 'suffix'),
        'email': person.email or '',
        'organizational_unit': org_full,
        'organizational_unit_short': org_short,
        'dienstort': dienstort,
        'organization_phone': org_phone,
        'organization_email': org_email,
        'visitenkarte_url': person.card or '',
    }


def _avatar_bytes(person):
    """Return raw image bytes for a CAMPUSonline person, or None.

    Prefers `Person.avatar_private` — a BinaryField holding the photo bytes
    directly in CAMPUSonline. This bypasses the per-person public-visibility
    gate that makes the public `avatar` URL return an HTML page for staff
    who've marked their photo internal-only.

    Falls back to downloading the public `avatar` URL if `avatar_private`
    is empty. Always validates that the result is actually an image."""
    from PIL import Image, UnidentifiedImageError

    private = getattr(person, 'avatar_private', None)
    if private:
        data = bytes(private)
        try:
            Image.open(io.BytesIO(data)).verify()
            return data
        except (UnidentifiedImageError, OSError) as e:
            logger.error(
                f"avatar_private for person {person.id} is not a valid image: {e}"
            )

    if person.avatar:
        try:
            response = requests.get(person.avatar, timeout=10)
            response.raise_for_status()
            Image.open(io.BytesIO(response.content)).verify()
            return response.content
        except (requests.RequestException, UnidentifiedImageError, OSError) as e:
            logger.error(
                f"Could not fetch avatar URL {person.avatar} for person "
                f"{person.id}: {e}"
            )

    return None


@login_required
def generate_my_pass(request):
    """Generate and download wallet pass for logged-in user"""
    if not CAMPUSONLINE_AVAILABLE:
        return HttpResponse(
            "<h1>SSO Not Available</h1>"
            "<p>This feature requires the full outpost.django infrastructure.</p>",
            status=503
        )

    username = request.user.username
    if not username:
        return HttpResponse(
            "<h1>Error</h1>"
            "<p>Could not determine your username from login.</p>",
            status=400
        )

    try:
        person = Person.objects.get(username=username)
    except Person.DoesNotExist:
        return HttpResponse(
            f"<h1>Person Not Found</h1>"
            f"<p>No CAMPUSonline person record found for username: {username}</p>",
            status=404
        )

    if not person.employed:
        return HttpResponse(
            "<h1>Not Eligible</h1>"
            "<p>Digital ID cards are only available to currently-employed staff.</p>",
            status=403,
        )

    employee_card, created = EmployeeCard.objects.update_or_create(
        employee_id=person.id,
        defaults=_person_to_card_defaults(person),
    )

    if not employee_card.photo:
        avatar_data = _avatar_bytes(person)
        if avatar_data:
            employee_card.photo.save(
                f'employee_{person.id}.jpg',
                ContentFile(avatar_data, name=f'employee_{person.id}.jpg'),
                save=True,
            )

    return apple_pass_download(request, employee_card.employee_id)


@login_required
def my_pass_preview(request):
    """Show preview page before generating pass"""
    lang = _resolve_language(request)
    with translation.override(lang):
        return _render_my_pass_preview(request, lang)


def _render_my_pass_preview(request, lang):
    if not CAMPUSONLINE_AVAILABLE:
        return render(request, 'idcard/error.html', {
            'error_title': 'SSO Not Available',
            'error_message': 'This feature requires the full outpost.django infrastructure.',
            'lang': lang,
        })

    username = request.user.username
    if not username:
        return render(request, 'idcard/error.html', {
            'error_title': 'Cannot identify user',
            'error_message': 'Could not determine your username from login.',
            'lang': lang,
        })

    try:
        person = Person.objects.get(username=username)
    except Person.DoesNotExist:
        return render(request, 'idcard/error.html', {
            'error_title': 'Person Not Found',
            'error_message': f'No CAMPUSonline person record found for username: {username}',
            'lang': lang,
        })

    if not person.employed:
        return render(request, 'idcard/error.html', {
            'error_title': 'Not Eligible',
            'error_message': 'Digital ID cards are only available to currently-employed staff.',
            'lang': lang,
        })

    try:
        employee_card = EmployeeCard.objects.get(employee_id=person.id)
        card_exists = True
    except EmployeeCard.DoesNotExist:
        employee_card = None
        card_exists = False

    device = _detect_device(request.META.get("HTTP_USER_AGENT", ""))
    page_url = request.build_absolute_uri(reverse("idcard:my_pass_preview"))
    qr_data_uri = _qr_data_uri(page_url) if device == "desktop" else None

    return render(request, 'idcard/my_pass_preview.html', {
        'employee_card': employee_card,
        'person': person,
        'card_exists': card_exists,
        'device': device,
        'lang': lang,
        'other_lang': "en" if lang == "de" else "de",
        'qr_data_uri': qr_data_uri,
    })
