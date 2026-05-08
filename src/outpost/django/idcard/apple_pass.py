"""
Apple Wallet Pass Generator

Pure Python implementation using OpenSSL for signing.
MedUni corporate design with larger photos and cleaner layout.
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
from PIL import Image
from .models import EmployeeCard

logger = logging.getLogger(__name__)


def generate_pass_json(employee):
    """Generate pass.json content for employee"""
    if not employee.apple_pass_serial:
        import uuid
        employee.apple_pass_serial = str(uuid.uuid4())
        employee.save()

    pass_data = {
        "formatVersion": 1,
        "passTypeIdentifier": settings.APPLE_PASS_TYPE_ID,
        "serialNumber": employee.apple_pass_serial,
        "teamIdentifier": settings.APPLE_TEAM_ID,
        "organizationName": "Medical University of Graz",
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

    sec.append({
        "key": "id",
        "label": "BEDIENSTETENNUMMER",
        "value": str(employee.employee_id),
    })
    if employee.organizational_unit_short:
        sec.append({
            "key": "oe_short",
            "label": "OE",
            "value": employee.organizational_unit_short,
        })

    if employee.email:
        aux.append({"key": "email", "label": "E-MAIL", "value": employee.email})

    if employee.organizational_unit:
        back.append({
            "key": "oe_full",
            "label": "Organisationseinheit",
            "value": employee.organizational_unit,
        })
    if employee.dienstort:
        back.append({"key": "dienstort", "label": "Dienstort", "value": employee.dienstort})
    if employee.organization_phone:
        back.append({
            "key": "oe_phone",
            "label": "Telefon (OE)",
            "value": employee.organization_phone,
        })
    if employee.organization_email:
        back.append({
            "key": "oe_email",
            "label": "E-Mail (OE)",
            "value": employee.organization_email,
        })

    if employee.visitenkarte_url:
        back.append({
            "key": "visitenkarte",
            "label": "Visitenkarte",
            "value": employee.visitenkarte_url,
        })
        pass_data["barcodes"] = [{
            "message": employee.visitenkarte_url,
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
        # Use paths from settings
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
    """
    Generate complete Apple Wallet pass (.pkpass file)
    
    Args:
        employee_id: Employee ID
        include_signature: Sign pass with certificates if True
    
    Returns:
        BytesIO containing the .pkpass file
    """
    employee = get_object_or_404(EmployeeCard, employee_id=employee_id)
    pass_files = {}
    
    # 1. pass.json
    pass_data = generate_pass_json(employee)
    pass_json = json.dumps(pass_data, indent=2).encode('utf-8')
    pass_files['pass.json'] = pass_json
    
    static_dir = os.path.join(os.path.dirname(__file__), 'static', 'idcard')
    
    # 2. Icons (required)
    icon_path = os.path.join(static_dir, 'icon.png')
    if os.path.exists(icon_path):
        with open(icon_path, 'rb') as f:
            pass_files['icon.png'] = f.read()
    
    icon_2x_path = os.path.join(static_dir, 'icon@2x.png')
    if os.path.exists(icon_2x_path):
        with open(icon_2x_path, 'rb') as f:
            pass_files['icon@2x.png'] = f.read()
    
    # 3. Logo
    logo_path = os.path.join(static_dir, 'logo.png')
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            pass_files['logo.png'] = f.read()
        
        logo_2x_path = os.path.join(static_dir, 'logo@2x.png')
        if os.path.exists(logo_2x_path):
            with open(logo_2x_path, 'rb') as f:
                pass_files['logo@2x.png'] = f.read()
    
    # 4. Employee photo thumbnail
    if employee.photo:
        try:
            img = Image.open(employee.photo.path)
            img.thumbnail((110, 110), Image.LANCZOS)
            
            thumb_buffer = BytesIO()
            img.save(thumb_buffer, format='PNG')
            pass_files['thumbnail.png'] = thumb_buffer.getvalue()
            
            # Retina version
            img_2x = Image.open(employee.photo.path)
            img_2x.thumbnail((220, 220), Image.LANCZOS)
            
            thumb_2x_buffer = BytesIO()
            img_2x.save(thumb_2x_buffer, format='PNG')
            pass_files['thumbnail@2x.png'] = thumb_2x_buffer.getvalue()
        except Exception as e:
            logger.error(f"Could not process photo for employee {employee.employee_id}: {e}")
    
    # 5. Manifest
    manifest_json = create_manifest(pass_files)
    
    # 6. Signature
    signature = None
    if include_signature:
        try:
            signature = sign_manifest(manifest_json)
        except Exception as e:
            raise Exception(f"Failed to sign pass: {str(e)}")
    
    # 7. Build .pkpass file
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
    """Download Apple Wallet pass for employee"""
    try:
        pass_data = generate_apple_pass(employee_id, include_signature=True)
        
        response = HttpResponse(
            pass_data.getvalue(),
            content_type='application/vnd.apple.pkpass'
        )
        response['Content-Disposition'] = f'attachment; filename="meduni_id_{employee_id}.pkpass"'
        
        return response
        
    except Exception as e:
        return HttpResponse(
            f"<h1>Error generating pass</h1>"
            f"<p>{str(e)}</p>"
            f"<p>Check that:</p>"
            f"<ul>"
            f"<li>APPLE_TEAM_ID is set in settings.py</li>"
            f"<li>APPLE_PASS_TYPE_ID is set in settings.py</li>"
            f"<li>Certificate files exist in credentials/ directory</li>"
            f"<li>Certificate password is correct</li>"
            f"</ul>",
            status=500
        )