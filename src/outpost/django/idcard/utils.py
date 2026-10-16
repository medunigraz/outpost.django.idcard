import hashlib
import json
import logging
import time
from io import BytesIO
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import (
    hashes,
    serialization,
)
from cryptography.hazmat.primitives.serialization import pkcs7
from google.auth import jwt
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from PIL import (
    Image,
    ImageDraw,
)

from .conf import settings

logger = logging.getLogger(__name__)

APPLE_IMAGES = ("icon.png", "icon@2x.png", "logo.png", "logo@2x.png")

GOOGLE_SCOPES = ["https://www.googleapis.com/auth/wallet_object.issuer"]
GOOGLE_WALLET_API = "https://walletobjects.googleapis.com/walletobjects/v1"
GOOGLE_PRIVATE_IMAGE_API = (
    "https://walletobjects.googleapis.com/upload/walletobjects/v1/privateContent"
)
GOOGLE_CLASS_SUFFIX = "meduni_employee_id"
GOOGLE_REQUIRED_SETTINGS = ("IDCARD_GOOGLE_ISSUER_ID", "IDCARD_GOOGLE_SERVICE_ACCOUNT")

# MedUni corporate dark green, the same colour the Apple pass sets as rgb(0, 124, 49).
GOOGLE_BACKGROUND = "#007c31"

_google_credentials = None


def silhouette(size):
    """Person silhouette for employees without a usable photo.

    White on transparent so the card's green shows through. Drawn at 4x and
    downsampled for clean edges.
    """
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


def square(data, size):
    """Center-crop image bytes to a square of the given size."""
    src = Image.open(BytesIO(data))
    short = min(src.width, src.height)
    left = (src.width - short) // 2
    top = (src.height - short) // 2
    return src.crop((left, top, left + short, top + short)).resize(
        (size, size), Image.LANCZOS
    )


def apple_images():
    """The static pass images. icon.png is the only one Apple requires."""
    static = Path(__file__).parent / "static" / "idcard"
    return {
        name: (static / name).read_bytes()
        for name in APPLE_IMAGES
        if (static / name).exists()
    }


def apple_manifest(files):
    """manifest.json with the SHA1 hash of every file in the pass."""
    manifest = {
        name: hashlib.sha1(content).hexdigest() for name, content in files.items()
    }
    return json.dumps(manifest, indent=2).encode("utf-8")


def pem(text):
    """PEM bytes from a settings string, tolerating indentation from pasting."""
    return "\n".join(line.strip() for line in text.strip().splitlines()).encode()


def apple_sign(manifest):
    """Detached PKCS#7 signature over the manifest, as Wallet requires."""
    password = settings.IDCARD_APPLE_KEY_PASSWORD
    cert = x509.load_pem_x509_certificate(pem(settings.IDCARD_APPLE_CERTIFICATE))
    wwdr = x509.load_pem_x509_certificate(pem(settings.IDCARD_APPLE_WWDR_CERTIFICATE))
    key = serialization.load_pem_private_key(
        pem(settings.IDCARD_APPLE_KEY), password.encode() if password else None
    )
    return (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(manifest)
        .add_signer(cert, key, hashes.SHA256())
        .add_certificate(wwdr)
        .sign(
            serialization.Encoding.DER,
            [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary],
        )
    )


def google_missing_settings():
    """Which required Google settings a fresh install has not configured yet."""
    return [name for name in GOOGLE_REQUIRED_SETTINGS if not getattr(settings, name)]


def google_credentials():
    """Service-account credentials, cached.

    The same credentials authorize the REST calls and sign the save link, which
    is why this runs headless.
    """
    global _google_credentials
    if _google_credentials is None:
        _google_credentials = service_account.Credentials.from_service_account_info(
            settings.IDCARD_GOOGLE_SERVICE_ACCOUNT, scopes=GOOGLE_SCOPES
        )
    return _google_credentials


def google_session():
    """An AuthorizedSession that mints and refreshes bearer tokens itself."""
    return AuthorizedSession(google_credentials())


def google_class_id():
    return f"{settings.IDCARD_GOOGLE_ISSUER_ID}.{GOOGLE_CLASS_SUFFIX}"


def google_localized(value, language="de-DE"):
    """Wrap a plain string in Google's LocalizedString shape."""
    return {"defaultValue": {"language": language, "value": value}}


def google_upsert_class():
    """Create or update the Generic pass class shared by all cards. Idempotent."""
    class_id = google_class_id()

    # Field values live on the object, but the card face layout is class
    # level. Without this override the photo renders only in the details
    # section. Google allows at most three rows; we use one.
    pass_class = {
        "id": class_id,
        "classTemplateInfo": {
            "cardTemplateOverride": {
                "cardRowTemplateInfos": [
                    {
                        "twoItems": {
                            "startItem": {
                                "firstValue": {
                                    "fields": [
                                        {
                                            "fieldPath": "object.textModulesData['employee_id']"
                                        }
                                    ],
                                },
                            },
                            "endItem": {
                                "firstValue": {
                                    "fields": [
                                        {
                                            "fieldPath": "object.imageModulesData['photo']"
                                        }
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
        session = google_session()
        resp = session.post(f"{GOOGLE_WALLET_API}/genericClass", json=pass_class)
        if resp.status_code == 409:
            resp = session.put(
                f"{GOOGLE_WALLET_API}/genericClass/{class_id}", json=pass_class
            )
        if resp.status_code not in (200, 201):
            logger.warning(
                f"Google Wallet class upsert returned {resp.status_code}: {resp.text}"
            )
    except Exception as e:
        logger.error(f"Error creating or updating the Google Wallet class: {e}")
    return class_id


def google_save_link(object_id):
    """Signed "Add to Google Wallet" link for an object Google already has."""
    creds = google_credentials()
    claims = {
        "iss": creds.service_account_email,
        "aud": "google",
        "typ": "savetowallet",
        "iat": int(time.time()),
        "payload": {"genericObjects": [{"id": object_id}]},
    }
    token = jwt.encode(creds.signer, claims).decode("utf-8")
    return f"https://pay.google.com/gp/v/save/{token}"
