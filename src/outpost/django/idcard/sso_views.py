"""
SSO Integration for Employee ID Card Generation

Integrates with outpost.django.campusonline for employee data.
Note: This module only works when deployed with the full outpost infrastructure.
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

# Conditional import - only available in full outpost deployment
try:
    from outpost.django.campusonline.models import Person
    CAMPUSONLINE_AVAILABLE = True
except ImportError:
    CAMPUSONLINE_AVAILABLE = False
    Person = None


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
            "<p>This feature requires the full outpost.django infrastructure.</p>"
            "<p>For local testing, use the admin interface to create employee cards manually.</p>",
            status=503
        )
    
    username = request.user.username
    
    if not username:
        return HttpResponse(
            "<h1>Error</h1>"
            "<p>Could not determine your username from login.</p>"
            "<p>Please contact IT support.</p>",
            status=400
        )
    
    try:
        person = Person.objects.get(username=username)
    except Person.DoesNotExist:
        return HttpResponse(
            f"<h1>Person Not Found</h1>"
            f"<p>No CAMPUSonline person record found for username: {username}</p>"
            f"<p>Please contact IT support.</p>",
            status=404
        )
    
    primary_org = person.organizations.first()
    org_name = primary_org.name if primary_org else ""
    
    employee_card, created = EmployeeCard.objects.update_or_create(
        employee_id=person.id,
        defaults={
            'first_name': person.first_name or '',
            'last_name': person.last_name or '',
            'email': person.email,
            'organizational_unit': org_name,
            'visitenkarte_url': person.card or '',
        }
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
            'error_message': 'This feature requires the full outpost.django infrastructure. For local testing, use the admin interface.'
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
            'error_message': f'No CAMPUSonline person record found for username: {username}'
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