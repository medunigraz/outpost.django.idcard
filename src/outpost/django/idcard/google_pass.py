"""
Google Wallet pass generator.

Nothing is downloaded here, unlike Apple. The card is pushed to Google over
REST and the user gets a signed "Add to Google Wallet" link. Both use the
service-account key, so it runs headless.

issuer -> class (one shared template) -> object (one per employee).

Generic passes carry their visual fields on the object, not the class. The
photo uses Secure Private Images so no public URL is ever created:
https://developers.google.com/wallet/generic/use-cases/secure-private-images
"""
import logging
import mimetypes
import time
import uuid

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils.html import escape

from .models import EmployeeCard

logger = logging.getLogger(__name__)

try:
    from google.oauth2 import service_account
    from google.auth import jwt as google_jwt
    from google.auth.transport.requests import AuthorizedSession
    GOOGLE_WALLET_AVAILABLE = True
except ImportError:
    GOOGLE_WALLET_AVAILABLE = False


SCOPES = ['https://www.googleapis.com/auth/wallet_object.issuer']
WALLET_API = 'https://walletobjects.googleapis.com/walletobjects/v1'
PRIVATE_IMAGE_UPLOAD_API = (
    'https://walletobjects.googleapis.com/upload/walletobjects/v1/privateContent'
)
CLASS_SUFFIX = 'meduni_employee_id'

# MedUni corporate dark green, same colour the Apple pass sets as rgb(0, 124, 49).
HEX_BACKGROUND = '#007c31'

_credentials = None


REQUIRED_SETTINGS = ('GOOGLE_WALLET_ISSUER_ID', 'GOOGLE_SERVICE_ACCOUNT_FILE')


def _missing_settings():
    """Which required settings a fresh install has not configured yet."""
    return [n for n in REQUIRED_SETTINGS if not getattr(settings, n, None)]


def _service_account_file():
    return str(getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', ''))


def get_authenticated_credentials():
    """Load (and cache) service-account credentials for the Wallet API.

    The same credentials object is used both to authorize REST calls and to
    sign the 'Add to Google Wallet' JWT (via its private key)."""
    global _credentials
    if _credentials is None:
        _credentials = service_account.Credentials.from_service_account_file(
            _service_account_file(), scopes=SCOPES
        )
    return _credentials


def _session():
    """An AuthorizedSession that mints/refreshes bearer tokens automatically."""
    return AuthorizedSession(get_authenticated_credentials())


def _class_id():
    return f"{settings.GOOGLE_WALLET_ISSUER_ID}.{CLASS_SUFFIX}"


def create_or_update_pass_class():
    """Create (or update) the shared Generic pass class. Idempotent."""
    class_id = _class_id()

    # Field values live on the object, but the card face layout is class
    # level. Without this override the photo renders only in the details
    # section. Google allows at most three rows; we use one.
    pass_class = {
        'id': class_id,
        'classTemplateInfo': {
            'cardTemplateOverride': {
                'cardRowTemplateInfos': [
                    {
                        'twoItems': {
                            'startItem': {
                                'firstValue': {
                                    'fields': [
                                        {
                                            'fieldPath':
                                                "object.textModulesData"
                                                "['employee_id']"
                                        },
                                    ],
                                },
                            },
                            'endItem': {
                                'firstValue': {
                                    'fields': [
                                        {
                                            'fieldPath':
                                                "object.imageModulesData"
                                                "['photo']"
                                        },
                                    ],
                                },
                            },
                        },
                    },
                ],
            },
        },
    }

    try:
        session = _session()
        resp = session.post(f"{WALLET_API}/genericClass", json=pass_class)
        if resp.status_code == 409:  # already exists -> update
            resp = session.put(
                f"{WALLET_API}/genericClass/{class_id}", json=pass_class
            )
        if resp.status_code not in (200, 201):
            logger.warning(
                "Google Wallet class upsert returned %s: %s",
                resp.status_code, resp.text,
            )
    except Exception as e:
        logger.error("Error creating/updating Google Wallet class: %s", e)
    return class_id


def _localized(value, language='de-DE'):
    """Wrap a plain string in Google's LocalizedString shape."""
    return {'defaultValue': {'language': language, 'value': value}}


def _upload_private_photo(employee):
    """Upload the photo as a secure private image, returning its id or None."""
    if not employee.photo:
        return None
    try:
        with employee.photo.open('rb') as f:
            data = f.read()
        content_type = mimetypes.guess_type(employee.photo.name)[0] or 'image/jpeg'
        url = f"{PRIVATE_IMAGE_UPLOAD_API}/{settings.GOOGLE_WALLET_ISSUER_ID}/uploadPrivateImage"
        resp = _session().post(url, data=data, headers={'Content-Type': content_type})
        if resp.status_code not in (200, 201):
            logger.warning(
                "Private photo upload failed for employee %s: %s %s",
                employee.employee_id, resp.status_code, resp.text,
            )
            return None
        return resp.json().get('privateImageId')
    except Exception as e:
        logger.error(
            "Error uploading private photo for employee %s: %s",
            employee.employee_id, e,
        )
        return None


def generate_pass_object(employee):
    """Build the Generic pass-object dict, mirroring the Apple field layout.

    Uploads the photo as a side effect when the employee has one.
    """
    issuer_id = settings.GOOGLE_WALLET_ISSUER_ID

    if not employee.google_pass_id:
        employee.google_pass_id = (
            f"{issuer_id}.{employee.employee_id}_{uuid.uuid4().hex[:8]}"
        )
        employee.save(update_fields=['google_pass_id'])

    pass_object = {
        'id': employee.google_pass_id,
        'classId': _class_id(),
        'genericType': 'GENERIC_TYPE_UNSPECIFIED',
        # state is ACTIVE here; Phase B flips it to EXPIRED on revocation.
        'state': 'ACTIVE',
        'hexBackgroundColor': HEX_BACKGROUND,
        'cardTitle': _localized('Medizinische Universität Graz'),
        'header': _localized(employee.full_name),
        'textModulesData': [
            {
                'id': 'employee_id',
                'header': 'Bedienstetennummer',
                'body': str(employee.employee_id),
            },
        ],
    }

    # Logo is optional: only include it if a URL is configured. Google fetches
    # it from a PUBLIC https URL, so this must point at a reachable raster image
    # (PNG/JPG, not SVG). In dev there's usually no public URL, so leave it empty.
    # In production point it at our own served static logo (e.g.
    # https://<host>/static/idcard/logo.png).
    logo_url = getattr(settings, 'GOOGLE_WALLET_LOGO_URL', '')
    if logo_url:
        pass_object['logo'] = {
            'sourceUri': {'uri': logo_url},
            'contentDescription': _localized('MedUni Graz Logo', 'en-US'),
        }

    private_image_id = _upload_private_photo(employee)
    if private_image_id:
        pass_object['imageModulesData'] = [{
            'id': 'photo',
            'mainImage': {
                'privateImageId': private_image_id,
                'contentDescription': _localized(
                    f'Foto von {employee.full_name}', 'de-DE'
                ),
            },
        }]

    if employee.organizational_unit_short:
        pass_object['subheader'] = _localized(employee.organizational_unit_short)

    text = pass_object['textModulesData']
    if employee.organizational_unit:
        text.append({
            'id': 'org_unit',
            'header': 'Organisationseinheit',
            'body': employee.organizational_unit,
        })
    if employee.dienstort:
        text.append({
            'id': 'dienstort',
            'header': 'Dienstort',
            'body': employee.dienstort,
        })
    if employee.email:
        text.append({
            'id': 'email',
            'header': 'E-Mail',
            'body': employee.email,
        })
    if employee.organization_phone:
        text.append({
            'id': 'oe_phone',
            'header': 'Telefon (OE)',
            'body': employee.organization_phone,
        })
    if employee.organization_email:
        text.append({
            'id': 'oe_email',
            'header': 'E-Mail (OE)',
            'body': employee.organization_email,
        })

    if employee.visitenkarte_url:
        pass_object['barcode'] = {
            'type': 'QR_CODE',
            'value': employee.visitenkarte_url,
        }
        pass_object['linksModuleData'] = {
            'uris': [{
                'uri': employee.visitenkarte_url,
                'description': 'Visitenkarte',
                'id': 'visitenkarte',
            }],
        }

    return pass_object


def create_or_update_pass_object(employee):
    """Push the employee's pass object to Google. Idempotent.

    Phase B reuses this exact path to propagate live updates and revocation
    (it just changes the object's fields / state before calling)."""
    try:
        pass_object = generate_pass_object(employee)
        session = _session()
        resp = session.post(f"{WALLET_API}/genericObject", json=pass_object)
        if resp.status_code == 409:  # already exists -> update
            resp = session.put(
                f"{WALLET_API}/genericObject/{employee.google_pass_id}",
                json=pass_object,
            )
        if resp.status_code not in (200, 201):
            logger.warning(
                "Google Wallet object upsert returned %s: %s",
                resp.status_code, resp.text,
            )
            return False
        return True
    except Exception as e:
        logger.error("Error creating/updating Google Wallet object: %s", e)
        return False


def generate_save_url(employee):
    """Upsert the class and object, then return a signed save link."""
    create_or_update_pass_class()
    if not create_or_update_pass_object(employee):
        # Signing a link to an object Google does not have would hand the user
        # an opaque Wallet error instead of ours. The logged warning from the
        # upsert carries Google's response body.
        raise RuntimeError(
            f"Google Wallet object upsert failed for employee "
            f"{employee.employee_id}; see the log for Google's response."
        )

    creds = get_authenticated_credentials()
    claims = {
        'iss': creds.service_account_email,
        'aud': 'google',
        'typ': 'savetowallet',
        'iat': int(time.time()),
        'payload': {
            'genericObjects': [{'id': employee.google_pass_id}],
        },
    }
    token = google_jwt.encode(creds.signer, claims).decode('utf-8')
    return f"https://pay.google.com/gp/v/save/{token}"


def google_pass_download(request, employee_id):
    """Redirect to the signed save link. Staff can add ?preview=1 for a page."""
    if not GOOGLE_WALLET_AVAILABLE:
        return HttpResponse(
            "<h1>Google Wallet Not Available</h1>"
            "<p>Required libraries not installed.</p>"
            "<p>Run: <code>pip install google-auth</code></p>",
            status=500,
        )

    missing = _missing_settings()
    if missing:
        names = ", ".join(missing)
        return HttpResponse(
            "<h1>Google Wallet Not Configured</h1>"
            f"<p>Unset in your Django settings: <code>{escape(names)}</code>.</p>"
            "<p>See the Settings section of the idcard README.</p>",
            status=503,
        )

    import os
    if not os.path.exists(_service_account_file()):
        return HttpResponse(
            "<h1>Google Wallet Not Configured</h1>"
            "<p>The service-account key is missing. Place "
            f"<code>{escape(_service_account_file())}</code> on the server "
            "and ensure its client_email is added to the issuer in the Wallet "
            "Business Console.</p>",
            status=503,
        )

    try:
        employee = get_object_or_404(EmployeeCard, employee_id=employee_id)
        save_url = generate_save_url(employee)
        if request.user.is_staff and request.GET.get('preview'):
            return render(request, 'idcard/google_wallet_add.html', {
                'employee': employee,
                'save_url': save_url,
            })
        return HttpResponseRedirect(save_url)
    except Exception as e:
        logger.exception("Google Wallet pass generation failed")
        return HttpResponse(
            "<h1>Error Generating Google Wallet Pass</h1>"
            f"<p>{escape(str(e))}</p>"
            "<p>Check that:</p><ul>"
            "<li>GOOGLE_WALLET_ISSUER_ID is set and matches the Business Console</li>"
            "<li>GOOGLE_SERVICE_ACCOUNT_FILE exists and is valid JSON</li>"
            "<li>The service account is added to the issuer (Developer access)</li>"
            "<li>The Google Wallet API is enabled on the Cloud project</li>"
            "</ul>",
            status=500,
        )


def update_google_pass(employee):
    """Phase B entry point: re-push an existing pass object (no-op if none)."""
    if not employee.google_pass_id:
        return False
    return create_or_update_pass_object(employee)
