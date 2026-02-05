"""
Google Wallet Pass Generator with OAuth2 Authentication

Uses OAuth2 client credentials (not service accounts).
First-time authentication required, then fully automated.
"""
import json
import uuid
import os
import logging
from datetime import datetime
from django.conf import settings
from django.shortcuts import get_object_or_404, render
from django.http import HttpResponse, HttpResponseRedirect
from .models import EmployeeCard

logger = logging.getLogger(__name__)

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    import requests
    GOOGLE_WALLET_AVAILABLE = True
except ImportError:
    GOOGLE_WALLET_AVAILABLE = False


SCOPES = ['https://www.googleapis.com/auth/wallet_object.issuer']
TOKEN_FILE = os.path.join(settings.BASE_DIR, 'credentials', 'google_wallet_token.json')


def get_authenticated_credentials():
    """Get OAuth2 credentials for Google Wallet API"""
    creds = None
    
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            logger.error(f"Error loading Google Wallet token: {e}")
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"Google Wallet token refresh failed: {e}")
                creds = None
        
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(settings.GOOGLE_OAUTH_CLIENT_FILE),
                SCOPES
            )
            creds = flow.run_local_server(port=8080)
        
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    
    return creds


def create_or_update_pass_class():
    """Create or update Google Wallet pass class (template)"""
    issuer_id = settings.GOOGLE_WALLET_ISSUER_ID
    class_suffix = 'meduni_employee_id'
    class_id = f"{issuer_id}.{class_suffix}"
    
    pass_class = {
        "id": class_id,
        "issuerName": "Medical University of Graz",
        "reviewStatus": "UNDER_REVIEW",
        "hexBackgroundColor": "#007c31",
        "logo": {
            "sourceUri": {
                "uri": settings.GOOGLE_WALLET_LOGO_URL
            },
            "contentDescription": {
                "defaultValue": {
                    "language": "en-US",
                    "value": "MedUni Graz Logo"
                }
            }
        },
        "localizedIssuerName": {
            "defaultValue": {
                "language": "en-US",
                "value": "Medical University of Graz"
            },
            "translations": [
                {
                    "language": "de-DE",
                    "value": "Medizinische Universität Graz"
                }
            ]
        }
    }
    
    try:
        creds = get_authenticated_credentials()
        creds.refresh(Request())
        
        headers = {
            'Authorization': f'Bearer {creds.token}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            'https://walletobjects.googleapis.com/walletobjects/v1/genericClass',
            headers=headers,
            json=pass_class
        )
        
        if response.status_code == 409:
            url = f"https://walletobjects.googleapis.com/walletobjects/v1/genericClass/{class_id}"
            response = requests.put(url, headers=headers, json=pass_class)
        
        if response.status_code in [200, 201]:
            return class_id
        else:
            logger.warning(f"Pass class creation warning: {response.status_code} - {response.text}")
            return class_id

    except Exception as e:
        logger.error(f"Error creating Google Wallet pass class: {e}")
        return class_id


def generate_pass_object(employee):
    """Generate Google Wallet pass object for an employee"""
    issuer_id = settings.GOOGLE_WALLET_ISSUER_ID
    class_suffix = 'meduni_employee_id'
    class_id = f"{issuer_id}.{class_suffix}"
    
    if not employee.google_pass_id:
        employee.google_pass_id = f"{issuer_id}.{employee.employee_id}_{uuid.uuid4().hex[:8]}"
        employee.save()
    
    pass_object = {
        "id": employee.google_pass_id,
        "classId": class_id,
        "state": "ACTIVE",
        "header": {
            "defaultValue": {
                "language": "en-US",
                "value": employee.full_name
            }
        },
        "textModulesData": [
            {
                "id": "employee_id",
                "header": "Employee ID",
                "body": str(employee.employee_id)
            }
        ]
    }
    
    if employee.photo:
        pass_object["heroImage"] = {
            "sourceUri": {
                "uri": employee.photo.url
            },
            "contentDescription": {
                "defaultValue": {
                    "language": "en-US",
                    "value": f"Photo of {employee.full_name}"
                }
            }
        }
    
    if employee.organizational_unit:
        pass_object["textModulesData"].append({
            "id": "org_unit",
            "header": "Organizational Unit",
            "body": employee.organizational_unit
        })
    
    if employee.email:
        pass_object["textModulesData"].append({
            "id": "email",
            "header": "Email",
            "body": employee.email
        })
    
    if employee.visitenkarte_url:
        pass_object["barcode"] = {
            "type": "QR_CODE",
            "value": employee.visitenkarte_url
        }
        
        pass_object["linksModuleData"] = {
            "uris": [
                {
                    "uri": employee.visitenkarte_url,
                    "description": "Employee Business Card",
                    "id": "visitenkarte"
                }
            ]
        }
    
    return pass_object


def create_or_update_pass_object(employee):
    """Create or update pass object in Google Wallet"""
    try:
        creds = get_authenticated_credentials()
        creds.refresh(Request())
        
        pass_object = generate_pass_object(employee)
        
        headers = {
            'Authorization': f'Bearer {creds.token}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            'https://walletobjects.googleapis.com/walletobjects/v1/genericObject',
            headers=headers,
            json=pass_object
        )
        
        if response.status_code == 409:
            url = f"https://walletobjects.googleapis.com/walletobjects/v1/genericObject/{employee.google_pass_id}"
            response = requests.put(url, headers=headers, json=pass_object)
        
        return response.status_code in [200, 201]

    except Exception as e:
        logger.error(f"Error creating/updating Google Wallet pass object: {e}")
        return False


def generate_save_url(employee):
    """Generate 'Add to Google Wallet' URL"""
    create_or_update_pass_class()
    create_or_update_pass_object(employee)
    save_url = f"https://pay.google.com/gp/v/save/{employee.google_pass_id}"
    return save_url


def google_pass_download(request, employee_id):
    """Generate Google Wallet pass for employee"""
    if not GOOGLE_WALLET_AVAILABLE:
        return HttpResponse(
            "<h1>Google Wallet Not Available</h1>"
            "<p>Required libraries not installed.</p>"
            "<p>Run: <code>pip install google-auth google-auth-oauthlib google-api-python-client</code></p>",
            status=500
        )
    
    try:
        employee = get_object_or_404(EmployeeCard, employee_id=employee_id)
        
        if not os.path.exists(TOKEN_FILE):
            return HttpResponse(
                "<h1>Google Wallet Authentication Required</h1>"
                "<p>First-time setup needed. Run this command in terminal:</p>"
                "<pre>python manage.py shell\n"
                "from outpost.django.idcard.google_pass import get_authenticated_credentials\n"
                "get_authenticated_credentials()</pre>"
                "<p>This will open a browser to authenticate. After that, this page will work automatically.</p>",
                status=401
            )
        
        save_url = generate_save_url(employee)
        
        return render(request, 'idcard/google_wallet_add.html', {
            'employee': employee,
            'save_url': save_url
        })
        
    except Exception as e:
        return HttpResponse(
            f"<h1>Error Generating Google Wallet Pass</h1>"
            f"<p>{str(e)}</p>"
            f"<p>Check that:</p>"
            f"<ul>"
            f"<li>GOOGLE_WALLET_ISSUER_ID is set in settings.py</li>"
            f"<li>GOOGLE_OAUTH_CLIENT_FILE exists in credentials/</li>"
            f"<li>Google Wallet API is enabled in Cloud Console</li>"
            f"<li>You've authenticated once (see instructions above)</li>"
            f"</ul>",
            status=500
        )


def update_google_pass(employee):
    """Update existing Google Wallet pass"""
    if not employee.google_pass_id:
        return False
    return create_or_update_pass_object(employee)