"""
Simple Apple Wallet Pass Generator (Pure Python - No M2Crypto!)

This generates the pass structure and creates the ZIP file.
Reads Team ID and Pass Type ID from Django settings.
"""
import json
import hashlib
import zipfile
from io import BytesIO
from datetime import datetime
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.conf import settings
from .models import EmployeeCard
import qrcode
from PIL import Image
import subprocess
import os


def generate_pass_json(employee):
    """
    Generate the pass.json content for an employee
    """
    if not employee.apple_pass_serial:
        import uuid
        employee.apple_pass_serial = str(uuid.uuid4())
        employee.save()
    
    # MedUni official colors from Corporate Design Manual
    pass_data = {
        "formatVersion": 1,
        "passTypeIdentifier": settings.APPLE_PASS_TYPE_ID,
        "serialNumber": employee.apple_pass_serial,
        "teamIdentifier": settings.APPLE_TEAM_ID,
        "organizationName": "Medical University of Graz",
        "description": f"MedUni Graz Employee ID - {employee.full_name}",
        
        # MedUni Corporate Design Colors!
        "backgroundColor": "rgb(0, 124, 60)",      # Dark Green #007c31
        "foregroundColor": "rgb(255, 255, 255)",    # White
        "labelColor": "rgb(255, 255, 255)",         # White
        
        "generic": {
            "primaryFields": [
                {
                    "key": "name",
                    "label": "NAME",
                    "value": employee.full_name
                }
            ],
            "secondaryFields": [],
            "auxiliaryFields": [],
            "backFields": []
        }
    }
    
    # Add organizational unit if exists
    if employee.organizational_unit:
        pass_data["generic"]["secondaryFields"].append({
            "key": "organization",
            "label": "ORGANIZATIONAL UNIT",
            "value": employee.organizational_unit
        })
    
    # Add back fields with details
    pass_data["generic"]["backFields"].append({
        "key": "about",
        "label": "About",
        "value": "This card identifies you as an employee of the Medical University of Graz."
    })
    
    if employee.visitenkarte_url:
        pass_data["generic"]["backFields"].append({
            "key": "visitenkarte",
            "label": "Business Card",
            "value": employee.visitenkarte_url
        })
    
    # Add QR code if Visitenkarte URL exists
    if employee.visitenkarte_url:
        pass_data["barcode"] = {
            "message": employee.visitenkarte_url,
            "format": "PKBarcodeFormatQR",
            "messageEncoding": "iso-8859-1",
            "altText": f"Scan for {employee.full_name}'s business card"
        }
        
        # Also add the newer barcodes array (iOS 9+)
        pass_data["barcodes"] = [
            {
                "message": employee.visitenkarte_url,
                "format": "PKBarcodeFormatQR",
                "messageEncoding": "iso-8859-1",
                "altText": f"Scan for {employee.full_name}'s business card"
            }
        ]
    
    return pass_data


def create_manifest(files_dict):
    """
    Create manifest.json with SHA1 hashes of all files
    """
    manifest = {}
    for filename, content in files_dict.items():
        sha1 = hashlib.sha1(content).hexdigest()
        manifest[filename] = sha1
    return json.dumps(manifest, indent=2).encode('utf-8')


def sign_manifest(manifest_json, cert_path, key_path, wwdr_path, password):
    """
    Sign the manifest using OpenSSL (called via subprocess)
    This creates the 'signature' file required by Apple
    """
    try:
        # Write manifest to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
            manifest_file = f.name
            f.write(manifest_json)
        
        # Create signature using OpenSSL
        signature_file = manifest_file + '.sig'
        
        # OpenSSL command to create PKCS7 signature
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
        
        # Read the signature
        with open(signature_file, 'rb') as f:
            signature = f.read()
        
        # Cleanup temp files
        os.unlink(manifest_file)
        os.unlink(signature_file)
        
        return signature
        
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to sign manifest: {e.stderr.decode()}")
    except Exception as e:
        raise Exception(f"Error during signing: {str(e)}")


def generate_apple_pass(employee_id, include_signature=True):
    """
    Generate a complete Apple Wallet pass as a ZIP file (.pkpass)
    
    Args:
        employee_id: Employee ID
        include_signature: If True, will attempt to sign the pass (requires certificates)
    
    Returns:
        BytesIO containing the .pkpass file
    """
    employee = get_object_or_404(EmployeeCard, employee_id=employee_id)
    
    # Dictionary to store all files that will go in the pass
    pass_files = {}
    
    # 1. Create pass.json
    pass_data = generate_pass_json(employee)
    pass_json = json.dumps(pass_data, indent=2).encode('utf-8')
    pass_files['pass.json'] = pass_json
    
    # 2. Add icon files (REQUIRED by Apple Wallet!)
    static_dir = os.path.join(settings.BASE_DIR, 'src', 'outpost', 'django', 'idcard', 'static', 'idcard')
    
    # Icons (29×29 and 58×58) - Required!
    icon_path = os.path.join(static_dir, 'icon.png')
    if os.path.exists(icon_path):
        with open(icon_path, 'rb') as f:
            pass_files['icon.png'] = f.read()
    
    icon_2x_path = os.path.join(static_dir, 'icon@2x.png')
    if os.path.exists(icon_2x_path):
        with open(icon_2x_path, 'rb') as f:
            pass_files['icon@2x.png'] = f.read()
    
    # Logos (160×50 and 320×100) - Optional but recommended
    logo_path = os.path.join(static_dir, 'logo.png')
    if os.path.exists(logo_path):
        with open(logo_path, 'rb') as f:
            pass_files['logo.png'] = f.read()
        
        logo_2x_path = os.path.join(static_dir, 'logo@2x.png')
        if os.path.exists(logo_2x_path):
            with open(logo_2x_path, 'rb') as f:
                pass_files['logo@2x.png'] = f.read()
    
    # 3. Add employee photo as thumbnail (if exists)
    if employee.photo:
        try:
            # Resize photo to 90x90 for thumbnail
            img = Image.open(employee.photo.path)
            img.thumbnail((90, 90), Image.LANCZOS)
            
            thumb_buffer = BytesIO()
            img.save(thumb_buffer, format='PNG')
            pass_files['thumbnail.png'] = thumb_buffer.getvalue()
            
            # Create @2x version (180x180)
            img_2x = Image.open(employee.photo.path)
            img_2x.thumbnail((180, 180), Image.LANCZOS)
            
            thumb_2x_buffer = BytesIO()
            img_2x.save(thumb_2x_buffer, format='PNG')
            pass_files['thumbnail@2x.png'] = thumb_2x_buffer.getvalue()
        except Exception as e:
            print(f"Could not process photo: {e}")
    
    # 4. Create manifest.json (SHA1 hashes of all files)
    manifest_json = create_manifest(pass_files)
    
    # 5. Sign the manifest
    signature = None
    if include_signature:
        try:
            cert_path = os.path.join(settings.BASE_DIR, 'certificates', 'pass_certificate.pem')
            key_path = os.path.join(settings.BASE_DIR, 'certificates', 'pass_key.pem')
            wwdr_path = os.path.join(settings.BASE_DIR, 'certificates', 'wwdr.pem')
            password = getattr(settings, 'APPLE_PASS_CERTIFICATE_PASSWORD', '')
            
            signature = sign_manifest(manifest_json, cert_path, key_path, wwdr_path, password)
        except Exception as e:
            raise Exception(f"Failed to sign pass: {str(e)}")
    
    # 6. Create the .pkpass ZIP file
    pkpass_buffer = BytesIO()
    with zipfile.ZipFile(pkpass_buffer, 'w', zipfile.ZIP_DEFLATED) as pkpass:
        # Add all pass files
        for filename, content in pass_files.items():
            pkpass.writestr(filename, content)
        
        # Add manifest
        pkpass.writestr('manifest.json', manifest_json)
        
        # Add signature if available
        if signature:
            pkpass.writestr('signature', signature)
    
    pkpass_buffer.seek(0)
    return pkpass_buffer


def apple_pass_download(request, employee_id):
    """
    View to download an Apple Wallet pass
    """
    try:
        # Generate signed pass
        pass_data = generate_apple_pass(employee_id, include_signature=True)
        
        response = HttpResponse(pass_data.getvalue(), content_type='application/vnd.apple.pkpass')
        response['Content-Disposition'] = f'attachment; filename="meduni_id_{employee_id}_signed.pkpass"'
        
        return response
        
    except Exception as e:
        return HttpResponse(
            f"<h1>Error generating pass</h1>"
            f"<p>{str(e)}</p>"
            f"<p>Check that:</p>"
            f"<ul>"
            f"<li>APPLE_TEAM_ID is set in settings.py</li>"
            f"<li>APPLE_PASS_TYPE_ID is set in settings.py</li>"
            f"<li>Certificate files exist in certificates/ directory</li>"
            f"<li>Certificate password is correct</li>"
            f"</ul>",
            status=500
        )