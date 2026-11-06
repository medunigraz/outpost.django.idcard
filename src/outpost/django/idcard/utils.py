import hashlib
import json
import logging
import ssl
import tempfile
import time
from io import BytesIO
from pathlib import Path

import httpx
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
    ImageChops,
    ImageDraw,
    ImageFont,
    ImageOps,
)

from .conf import settings

logger = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static" / "idcard"
APPLE_IMAGES = ("icon.png", "icon@2x.png", "logo.png", "logo@2x.png", "logo@3x.png")
# Store card strip in points; the artwork is drawn at @3x.
APPLE_STRIP_SIZE = (375, 144)
# Med Uni Graz Dunkelgrün and Grau 1 from the corporate design manual.
APPLE_BACKGROUND = (0, 124, 50)
APPLE_REVOKED_BACKGROUND = "rgb(107, 109, 116)"
# Ubuntu is the corporate font. Variable font, set to Medium.
APPLE_FONT = Path(__file__).parent / "fonts" / "Ubuntu.ttf"
APPLE_FONT_WEIGHT = 500
# How much of the card green covers the artwork behind the name, instead of a
# text shadow (the manual rules out font effects).
APPLE_WASH = 0.75
# Font sizes in points, largest first; text that fits at none gets an ellipsis.
APPLE_NAME_SIZES = range(28, 17, -1)
APPLE_TITLE_SIZES = (13, 12, 11)
# Pass updates are only delivered by the production environment, never the sandbox.
APNS_URL = "https://api.push.apple.com/3/device"

GOOGLE_SCOPES = ["https://www.googleapis.com/auth/wallet_object.issuer"]
GOOGLE_WALLET_API = "https://walletobjects.googleapis.com/walletobjects/v1"
GOOGLE_PRIVATE_IMAGE_API = (
    "https://walletobjects.googleapis.com/upload/walletobjects/v1/privateContent"
)
GOOGLE_CLASS_SUFFIX = "meduni_employee_id"
GOOGLE_REQUIRED_SETTINGS = ("IDCARD_GOOGLE_ISSUER_ID", "IDCARD_GOOGLE_SERVICE_ACCOUNT")

# The same colours as the Apple pass. Revoked cards turn grey on both platforms.
GOOGLE_BACKGROUND = "#007c32"
GOOGLE_REVOKED_BACKGROUND = "#6b6d74"

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


def cover(data, width, height):
    """Crop image bytes to fill width x height, keeping faces in the upper part."""
    src = Image.open(BytesIO(data)).convert("RGBA")
    return ImageOps.fit(src, (width, height), Image.LANCZOS, centering=(0.5, 0.4))


def wrap(text, font, width, lines=2):
    """Break text at spaces into at most `lines` lines, ellipsis if it still overflows."""
    out = [""]
    for word in text.split():
        candidate = f"{out[-1]} {word}".strip()
        if not out[-1] or font.getlength(candidate) <= width:
            out[-1] = candidate
        else:
            out.append(word)
    fits = len(out) <= lines and all(font.getlength(line) <= width for line in out)
    if not fits:
        cut = len(out) > lines
        out = out[:lines]
        for i, line in enumerate(out):
            if (cut and i == len(out) - 1) or font.getlength(line) > width:
                while line and font.getlength(line + "…") > width:
                    line = line[:-1]
                out[i] = line.rstrip() + "…"
    return out, fits


def apple_strip(data, scale, name=None):
    """Campus artwork over the card green, the photo framed on the right, the name beside it.

    Wallet draws a store card's primary field across the whole strip, so the
    name is drawn here instead. With `data` None the frame holds the silhouette.
    """
    width, height = APPLE_STRIP_SIZE[0] * scale, APPLE_STRIP_SIZE[1] * scale
    strip = Image.new("RGBA", (width, height), APPLE_BACKGROUND + (255,))
    art = Image.open(STATIC / "strip-campus.png").convert("RGBA")
    strip.alpha_composite(art.resize((width, height), Image.LANCZOS))

    photo_h = round(height * 0.78)
    photo_w = round(photo_h * 0.8)
    if data:
        photo = cover(data, photo_w, photo_h)
    else:
        photo = Image.new("RGBA", (photo_w, photo_h), (255, 255, 255, 40))
        photo.alpha_composite(silhouette(photo_w), (0, photo_h - photo_w))

    radius, border = 6 * scale, 2 * scale
    mask = Image.new("L", photo.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, photo_w - 1, photo_h - 1), radius, fill=255
    )
    photo.putalpha(ImageChops.multiply(photo.getchannel("A"), mask))

    x, y = width - photo_w - 16 * scale, (height - photo_h) // 2
    if name:
        wash(strip, x)
    strip.alpha_composite(photo, (x, y))
    ImageDraw.Draw(strip).rounded_rectangle(
        (x, y, x + photo_w - 1, y + photo_h - 1),
        radius,
        outline=(255, 255, 255, 255),
        width=border,
    )
    if name:
        draw_name(strip, name, scale, 16 * scale, x - 16 * scale, y + photo_h // 2)
    return strip.convert("RGB")


def wash(strip, right):
    """Card green over the artwork left of `right`, fading out towards it."""
    ramp = Image.new("L", (strip.width, 1))
    for i in range(strip.width):
        v = 1 - (i - right * 0.55) / (right * 0.45)
        ramp.putpixel((i, 0), int(APPLE_WASH * 255 * max(0, min(1, v))))
    layer = Image.new("RGBA", strip.size, APPLE_BACKGROUND + (0,))
    layer.putalpha(ramp.resize(strip.size))
    strip.alpha_composite(layer)


def fit(text, sizes, width, lines):
    """The largest font that fits text into `lines` lines, else the smallest, cut."""
    for size in sizes:
        font = ImageFont.truetype(str(APPLE_FONT), size)
        font.set_variation_by_axes([100, APPLE_FONT_WEIGHT])
        out, fits = wrap(text, font, width, lines)
        if fits:
            break
    return [(line, font) for line in out]


def draw_name(strip, name, scale, left, right, middle):
    """Name in up to two lines, titles small above and below, centred on middle.

    `name` is (title prefix, first and last name, post-nominal), so a long
    title can never push the surname off the strip.
    """
    prefix, name, suffix = name
    width = right - left
    titles = [s * scale for s in APPLE_TITLE_SIZES]
    rows = fit(name, [s * scale for s in APPLE_NAME_SIZES], width, 2)
    if prefix:
        rows = fit(prefix, titles, width, 1) + rows
    if suffix:
        rows += fit(suffix, titles, width, 1)
    heights = [round(font.size * 1.2) for _, font in rows]
    top = middle - sum(heights) // 2
    draw = ImageDraw.Draw(strip)
    for (line, font), height in zip(rows, heights):
        draw.text((left, top + height // 2), line, font=font, fill="white", anchor="lm")
        top += height


def apple_images():
    """The static pass images. icon.png is the only one Apple requires."""
    return {
        name: (STATIC / name).read_bytes()
        for name in APPLE_IMAGES
        if (STATIC / name).exists()
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


def apns_ssl_context():
    """TLS client context authenticating as the Pass Type ID certificate.

    ssl only loads a certificate chain from files, so they exist for the
    duration of this call only.
    """
    context = ssl.create_default_context()
    with tempfile.TemporaryDirectory() as tmp:
        cert, key = Path(tmp) / "cert.pem", Path(tmp) / "key.pem"
        cert.write_bytes(pem(settings.IDCARD_APPLE_CERTIFICATE))
        key.write_bytes(pem(settings.IDCARD_APPLE_KEY))
        context.load_cert_chain(cert, key, password=settings.IDCARD_APPLE_KEY_PASSWORD)
    return context


def apns_push(tokens):
    """Send Wallet's empty update push to each device. Returns the tokens APNs no longer knows."""
    gone = []
    with httpx.Client(http2=True, verify=apns_ssl_context(), timeout=10) as client:
        for token in tokens:
            try:
                resp = client.post(
                    f"{APNS_URL}/{token}",
                    headers={"apns-topic": settings.IDCARD_APPLE_PASS_TYPE_ID},
                    content=b"{}",
                )
            except httpx.HTTPError as e:
                logger.error(f"APNs push failed: {e}")
                continue
            if resp.status_code == 410:
                gone.append(token)
            elif resp.status_code != 200:
                logger.warning(f"APNs push returned {resp.status_code}: {resp.text}")
    return gone


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


def google_image(name, description):
    """An image Google fetches from IDCARD_GOOGLE_IMAGE_URL, so it must be public."""
    base = settings.IDCARD_GOOGLE_IMAGE_URL.rstrip("/")
    return {
        "sourceUri": {"uri": f"{base}/{name}"},
        "contentDescription": google_localized(description),
    }


def google_upsert_class():
    """Create or update the Generic pass class shared by all cards. Idempotent."""
    class_id = google_class_id()

    # Field values live on the object, but the card face layout is class
    # level. Without this override the photo renders only in the details
    # section. Google allows at most three rows; we use all of them.
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
                    {
                        "oneItem": {
                            "item": {
                                "firstValue": {
                                    "fields": [
                                        {
                                            "fieldPath": "object.textModulesData['org_unit']"
                                        }
                                    ],
                                },
                            },
                        },
                    },
                    {
                        "oneItem": {
                            "item": {
                                "firstValue": {
                                    "fields": [
                                        {"fieldPath": "object.textModulesData['email']"}
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
