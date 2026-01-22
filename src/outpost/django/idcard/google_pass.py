"""
Google Wallet Pass Generator

JWT-based pass generation with REST API.
Passes stored on Google's servers, can be updated dynamically.
"""
import json
import uuid
from datetime import datetime
from django.conf import settings
from django.shortcuts import get_object_or_404, render
from django.http import HttpResponse
from .models import EmployeeCard

try:
    from google.auth import crypt, jwt
    from google.oauth2 import service_account
    import requests
    GOOGLE_WALLET_AVAILABLE = True
except ImportError:
    GOOGLE_WALLET_AVAILABLE = False


def get_service_account_credentials():
    """Load Google Wallet API service account credentials"""
    if not GOOGLE_WALLET_AVAILABLE:
        raise Exception(
            "Google Wallet libraries not installed. "
            "Run: pip install google-auth requests"
        )
    
    service_account_file = getattr(
        settings, 
        'GOOGLE_WALLET_SERVICE_ACCOUNT_FILE',
        'certificates/google_service_account.json'
    )
    
    try:
        credentials = service_account.Credentials.from_service_account_file(
            service_account_file,
            scopes=['https://www.googleapis.com/auth/wallet_object.issuer']
        )
        return credentials
    except FileNotFoundError:
        raise Exception(
            f"Service account file not found: {service_account_file}\n"
            "Please create Google Cloud service account and download JSON key."
        )


def create_google_pass_class(credentials):
    """
    Create or update Google Wallet pass class (template)
    
    Defines design/structure for all employee ID passes.
    Only needs to be called once, reused for all employees.
    """
    issuer_id = getattr(settings, 'GOOGLE_WALLET_ISSUER_ID', 'YOUR_ISSUER_ID')
    class_suffix = 'meduni_employee_id'
    class_id = f"{issuer_id}.{class_suffix}"
    
    pass_class = {
        "id": class_id,
        "issuerName": "Medical University of Graz",
        "reviewStatus": "UNDER_REVIEW",  # Change to APPROVED after Google reviews
        "logo": {
            "sourceUri": {
                "uri": getattr(
                    settings, 
                    'GOOGLE_WALLET_LOGO_URL',
                    'https://www.medunigraz.at/fileadmin/templates/img/logo.png'
                )
            },
            "contentDescription": {
                "defaultValue": {
                    "language": "en-US",
                    "value": "MedUni Graz Logo"
                }
            }
        },
        "hexBackgroundColor": "#007c31",
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
    
    credentials.refresh(requests.Request())
    headers = {
        'Authorization': f'Bearer {credentials.token}',
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
    
    if response.status_code not in [200, 201]:
        print(f"Warning: Pass class creation failed: {response.text}")
        return False
    
    return True


def generate_google_pass_data(employee):
    """Generate pass object data for employee"""
    issuer_id = getattr(settings, 'GOOGLE_WALLET_ISSUER_ID', 'YOUR_ISSUER_ID')
    class_suffix = 'meduni_employee_id'
    
    if not employee.google_pass_id:
        employee.google_pass_id = f"{issuer_id}.{employee.employee_id}_{uuid.uuid4().hex[:8]}"
        employee.save()
    
    class_id = f"{issuer_id}.{class_suffix}"
    
    pass_object = {
        "id": employee.google_pass_id,
        "classId": class_id,
        "state": "ACTIVE",
        "logo": {
            "sourceUri": {
                "uri": employee.photo.url if employee.photo else ""
            },
            "contentDescription": {
                "defaultValue": {
                    "language": "en-US",
                    "value": f"Photo of {employee.full_name}"
                }
            }
        } if employee.photo else None,
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
        ],
        "barcode": {
            "type": "QR_CODE",
            "value": employee.visitenkarte_url
        } if employee.visitenkarte_url else None,
        "linksModuleData": {
            "uris": [
                {
                    "uri": "https://www.medunigraz.at",
                    "description": "Medical University of Graz",
                    "id": "meduni_website"
                }
            ]
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
    
    return {k: v for k, v in pass_object.items() if v is not None}


def create_google_pass_jwt(employee):
    """Create signed JWT for adding pass to Google Wallet"""
    credentials = get_service_account_credentials()
    create_google_pass_class(credentials)
    pass_object = generate_google_pass_data(employee)
    
    payload = {
        "iss": credentials.service_account_email,
        "aud": "google",
        "typ": "savetowallet",
        "iat": int(datetime.utcnow().timestamp()),
        "origins": [
            getattr(settings, 'GOOGLE_WALLET_ORIGIN', 'https://api.medunigraz.at')
        ],
        "payload": {
            "genericObjects": [pass_object]
        }
    }
    
    signer = crypt.RSASigner.from_service_account_file(
        getattr(
            settings,
            'GOOGLE_WALLET_SERVICE_ACCOUNT_FILE',
            'certificates/google_service_account.json'
        )
    )
    
    token = jwt.encode(signer, payload)
    return token.decode('utf-8')


def google_pass_download(request, employee_id):
    """Generate Google Wallet pass link for employee"""
    if not GOOGLE_WALLET_AVAILABLE:
        return HttpResponse(
            "<h1>Google Wallet Not Available</h1>"
            "<p>Required libraries not installed.</p>"
            "<p>Run: <code>pip install google-auth requests</code></p>",
            status=500
        )
    
    try:
        employee = get_object_or_404(EmployeeCard, employee_id=employee_id)
        jwt_token = create_google_pass_jwt(employee)
        save_url = f"https://pay.google.com/gp/v/save/{jwt_token}"
        
        return render(request, 'idcard/google_wallet_add.html', {
            'employee': employee,
            'save_url': save_url,
            'jwt_token': jwt_token
        })
        
    except Exception as e:
        return HttpResponse(
            f"<h1>Error Generating Google Wallet Pass</h1>"
            f"<p>{str(e)}</p>"
            f"<p>Check that:</p>"
            f"<ul>"
            f"<li>GOOGLE_WALLET_ISSUER_ID is set in settings.py</li>"
            f"<li>Service account JSON file exists</li>"
            f"<li>Google Wallet API is enabled in Cloud Console</li>"
            f"<li>Service account has 'Wallet Object Issuer' role</li>"
            f"</ul>",
            status=500
        )


def update_google_pass(employee):
    """
    Update existing Google Wallet pass
    
    Advantage: Updates appear immediately in user's wallet
    without requiring new download.
    """
    if not employee.google_pass_id:
        return False
    
    try:
        credentials = get_service_account_credentials()
        credentials.refresh(requests.Request())
        pass_object = generate_google_pass_data(employee)
        
        url = f"https://walletobjects.googleapis.com/walletobjects/v1/genericObject/{employee.google_pass_id}"
        headers = {
            'Authorization': f'Bearer {credentials.token}',
            'Content-Type': 'application/json'
        }
        
        response = requests.put(url, headers=headers, json=pass_object)
        return response.status_code == 200
        
    except Exception as e:
        print(f"Error updating Google Wallet pass: {e}")
        return False