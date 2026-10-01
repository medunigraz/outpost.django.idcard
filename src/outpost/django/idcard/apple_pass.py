"""
Apple Wallet pass generator.

Builds a .pkpass in memory: pass.json plus images, a manifest of SHA1 hashes,
and a detached PKCS#7 signature over that manifest. Signing shells out to the
openssl binary, so the server needs one on PATH.
"""
import json
import hashlib
import zipfile
import tempfile
import subprocess
import os
import logging
from io import BytesIO
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.conf import settings
from django.utils import translation
from django.utils.html import escape
from PIL import Image, ImageDraw, UnidentifiedImageError
from .models import EmployeeCard

logger = logging.getLogger(__name__)


def _silhouette_thumbnail(size):
    """Generic person-silhouette PNG used when an employee has no usable photo.
    White on transparent so the card's green background shows through.
    Drawn at 4× and downsampled with LANCZOS for clean edges."""
    scale = 4
    big = size * scale
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fill = (255, 255, 255, 230)

    head_r = big * 0.18
    head_cx, head_cy = big / 2, big * 0.32
    draw.ellipse(
        [head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r],
        fill=fill,
    )

    body_w, body_h = big * 0.78, big * 1.10
    body_left = (big - body_w) / 2
    body_top = big * 0.58
    draw.ellipse(
        [body_left, body_top, body_left + body_w, body_top + body_h],
        fill=fill,
    )

    return img.resize((size, size), Image.LANCZOS)


def _build_thumbnail(employee, size):
    """Real photo (center-cropped to square) when available and valid;
    otherwise the silhouette placeholder."""
    avatar = employee.person.avatar_private
    if avatar:
        try:
            src = Image.open(BytesIO(bytes(avatar)))
            short = min(src.width, src.height)
            left = (src.width - short) // 2
            top = (src.height - short) // 2
            square = src.crop((left, top, left + short, top + short))
            return square.resize((size, size), Image.LANCZOS)
        except (UnidentifiedImageError, OSError) as e:
            logger.error(
                f"Could not process photo for employee {employee.person_id}: "
                f"{e}; falling back to silhouette."
            )
    return _silhouette_thumbnail(size)


@translation.override("de")
def generate_pass_json(employee):
    """Generate pass.json content for employee"""
    if not employee.apple_pass_serial:
        import uuid
        employee.apple_pass_serial = str(uuid.uuid4())
        employee.save()

    person = employee.person
    org = employee.organization

    pass_data = {
        "formatVersion": 1,
        "passTypeIdentifier": settings.APPLE_PASS_TYPE_ID,
        "serialNumber": employee.apple_pass_serial,
        "teamIdentifier": settings.APPLE_TEAM_ID,
        "organizationName": "MedUni Graz",
        "description": f"MedUni Graz Employee ID - {employee.full_name}",
        "backgroundColor": "rgb(0, 124, 49)",
        "foregroundColor": "rgb(255, 255, 255)",
        "labelColor": "rgb(255, 255, 255)",
        "generic": {
            "primaryFields": [
                {"key": "name", "label": "NAME", "value": employee.full_name}
            ],
            "secondaryFields": [],
            "auxiliaryFields": [],
            "backFields": [],
        },
    }

    sec = pass_data["generic"]["secondaryFields"]
    aux = pass_data["generic"]["auxiliaryFields"]
    back = pass_data["generic"]["backFields"]

    if org and org.short:
        sec.append({
            "key": "oe_short",
            "label": "OE",
            "value": org.short,
        })

    aux.append({
        "key": "id",
        "label": "BEDIENSTETENNUMMER",
        "value": str(employee.person_id),
    })
    if person.email:
        aux.append({"key": "email", "label": "E-MAIL", "value": person.email})

    if employee.organization_name:
        back.append({
            "key": "oe_full",
            "label": "Organisationseinheit",
            "value": employee.organization_name,
        })
    if org and org.address:
        back.append({"key": "dienstort", "label": "Dienstort", "value": org.address})
    if org and org.phone:
        back.append({
            "key": "oe_phone",
            "label": "Telefon (OE)",
            "value": org.phone,
        })
    if org and org.email:
        back.append({
            "key": "oe_email",
            "label": "E-Mail (OE)",
            "value": org.email,
        })

    if person.card:
        back.append({
            "key": "visitenkarte",
            "label": "Visitenkarte",
            "value": person.card,
        })
        pass_data["barcodes"] = [{
            "message": person.card,
            "format": "PKBarcodeFormatQR",
            "messageEncoding": "iso-8859-1",
        }]

    back.append({
        "key": "about",
        "label": "About",
        "value": "This card identifies you as an employee of the Medical University of Graz.",
    })

    return pass_data


def create_manifest(files_dict):
    """Create manifest.json with SHA1 hashes"""
    manifest = {}
    for filename, content in files_dict.items():
        sha1 = hashlib.sha1(content).hexdigest()
        manifest[filename] = sha1
    return json.dumps(manifest, indent=2).encode('utf-8')


def sign_manifest(manifest_json):
    """Sign manifest using OpenSSL to create PKCS7 signature"""
    try:
        cert_path = str(settings.APPLE_PASS_CERT_PATH)
        key_path = str(settings.APPLE_PASS_KEY_PATH)
        wwdr_path = str(settings.APPLE_WWDR_PATH)
        password = settings.APPLE_PASS_CERTIFICATE_PASSWORD
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
            manifest_file = f.name
            f.write(manifest_json)
        
        signature_file = manifest_file + '.sig'
        
        cmd = [
            'openssl', 'smime', '-binary', '-sign',
            '-certfile', wwdr_path,
            '-signer', cert_path,
            '-inkey', key_path,
            '-in', manifest_file,
            '-out', signature_file,
            '-outform', 'DER'
        ]
        
        if password:
            cmd.extend(['-passin', f'pass:{password}'])
        
        subprocess.run(cmd, check=True, capture_output=True)
        
        with open(signature_file, 'rb') as f:
            signature = f.read()
        
        os.unlink(manifest_file)
        os.unlink(signature_file)
        
        return signature
        
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to sign manifest: {e.stderr.decode()}")
    except Exception as e:
        raise Exception(f"Error during signing: {str(e)}")


def generate_apple_pass(employee_id, include_signature=True):
    """Build the .pkpass for an employee and return it as a BytesIO.

    Pass `include_signature=False` to skip signing, which produces a file
    Wallet will reject but which can still be unzipped and inspected.
    """
    employee = get_object_or_404(
        EmployeeCard.objects.select_related('person'), person_id=employee_id
    )
    pass_files = {}

    pass_data = generate_pass_json(employee)
    pass_json = json.dumps(pass_data, indent=2).encode('utf-8')
    pass_files['pass.json'] = pass_json

    static_dir = os.path.join(os.path.dirname(__file__), 'static', 'idcard')

    # icon.png is the only image Apple requires.
    icon_path = os.path.join(static_dir, 'icon.png')
    if os.path.exists(icon_path):
        with open(icon_path, 'rb') as f:
            pass_files['icon.png'] = f.read()
    
    icon_2x_path = os.path.join(static_dir, 'icon@2x.png')
    if os.path.exists(icon_2x_path):
        with open(icon_2x_path, 'rb') as f:
            pass_files['icon@2x.png'] = f.read()
    
    logo_path = os.path.join(static_dir, 'logo.png')
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            pass_files['logo.png'] = f.read()
        
        logo_2x_path = os.path.join(static_dir, 'logo@2x.png')
        if os.path.exists(logo_2x_path):
            with open(logo_2x_path, 'rb') as f:
                pass_files['logo@2x.png'] = f.read()
    
    # Apple fixes the thumbnail at 90×90pt, so 180×180 for the @2x variant.
    for size, key in ((90, 'thumbnail.png'), (180, 'thumbnail@2x.png')):
        thumb = _build_thumbnail(employee, size)
        buf = BytesIO()
        thumb.save(buf, format='PNG')
        pass_files[key] = buf.getvalue()

    manifest_json = create_manifest(pass_files)

    signature = None
    if include_signature:
        signature = sign_manifest(manifest_json)

    pkpass_buffer = BytesIO()
    with zipfile.ZipFile(pkpass_buffer, 'w', zipfile.ZIP_DEFLATED) as pkpass:
        for filename, content in pass_files.items():
            pkpass.writestr(filename, content)
        pkpass.writestr('manifest.json', manifest_json)
        if signature:
            pkpass.writestr('signature', signature)
    
    pkpass_buffer.seek(0)
    return pkpass_buffer


def apple_pass_download(request, employee_id):
    """Serve the signed .pkpass as a download."""
    try:
        pass_data = generate_apple_pass(employee_id, include_signature=True)

        response = HttpResponse(
            pass_data.getvalue(),
            content_type='application/vnd.apple.pkpass'
        )
        response['Content-Disposition'] = f'attachment; filename="meduni_id_{employee_id}.pkpass"'

        return response

    except Exception as e:
        logger.exception(
            "Apple Wallet pass generation failed for employee %s", employee_id
        )
        return HttpResponse(
            f"<h1>Error generating pass</h1>"
            f"<p>{escape(str(e))}</p>"
            f"<p>Check that:</p>"
            f"<ul>"
            f"<li>APPLE_TEAM_ID and APPLE_PASS_TYPE_ID are set in your Django settings</li>"
            f"<li>APPLE_PASS_CERT_PATH, APPLE_PASS_KEY_PATH and APPLE_WWDR_PATH point at readable files</li>"
            f"<li>APPLE_PASS_CERTIFICATE_PASSWORD matches the key</li>"
            f"<li>the openssl binary is on PATH</li>"
            f"</ul>",
            status=500
        )