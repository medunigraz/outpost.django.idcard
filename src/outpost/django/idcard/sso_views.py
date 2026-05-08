"""
SSO Integration for Employee ID Card Generation

Integrates with outpost.django.campusonline for employee data.
"""
import logging
import requests
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.core.files.base import ContentFile
from .models import EmployeeCard
from .apple_pass import apple_pass_download

logger = logging.getLogger(__name__)

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


def download_avatar(avatar_url):
    """Download avatar image from URL"""
    try:
        response = requests.get(avatar_url, timeout=10)
        response.raise_for_status()
        filename = avatar_url.split('/')[-1] or 'avatar.jpg'
        return ContentFile(response.content, name=filename)
    except requests.RequestException as e:
        logger.error(f"Error downloading avatar from {avatar_url}: {e}")
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

    if person.avatar and not employee_card.photo:
        avatar_file = download_avatar(person.avatar)
        if avatar_file:
            employee_card.photo.save(
                f'employee_{person.id}.jpg',
                avatar_file,
                save=True
            )

    return apple_pass_download(request, employee_card.employee_id)


@login_required
def my_pass_preview(request):
    """Show preview page before generating pass"""
    if not CAMPUSONLINE_AVAILABLE:
        return render(request, 'idcard/error.html', {
            'error_title': 'SSO Not Available',
            'error_message': 'This feature requires the full outpost.django infrastructure.'
        })

    username = request.user.username
    if not username:
        return render(request, 'idcard/error.html', {
            'error_title': 'Cannot identify user',
            'error_message': 'Could not determine your username from login.'
        })

    try:
        person = Person.objects.get(username=username)
    except Person.DoesNotExist:
        return render(request, 'idcard/error.html', {
            'error_title': 'Person Not Found',
            'error_message': f'No CAMPUSonline person record found for username: {username}',
        })

    if not person.employed:
        return render(request, 'idcard/error.html', {
            'error_title': 'Not Eligible',
            'error_message': 'Digital ID cards are only available to currently-employed staff.',
        })

    try:
        employee_card = EmployeeCard.objects.get(employee_id=person.id)
        card_exists = True
    except EmployeeCard.DoesNotExist:
        employee_card = None
        card_exists = False

    organizations = person.organizations.all()

    return render(request, 'idcard/my_pass_preview.html', {
        'employee_card': employee_card,
        'person': person,
        'organizations': organizations,
        'card_exists': card_exists,
    })
