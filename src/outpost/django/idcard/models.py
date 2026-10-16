import json
import logging
import uuid
import zipfile
from functools import cached_property
from io import BytesIO

from django.db import models
from django.utils import translation
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _
from PIL import UnidentifiedImageError

from . import utils
from .conf import settings

logger = logging.getLogger(__name__)


def _title_part(hstore, key):
    if isinstance(hstore, dict):
        return hstore.get(key) or ""
    return ""


def _localized(value):
    """Resolve an HStoreField multilingual dict to the active language, German first."""
    if isinstance(value, dict):
        lang = (get_language() or "de").split("-")[0]
        return (
            value.get(lang) or value.get("de") or next(iter(value.values()), "") or ""
        )
    return value or ""


class EmployeeCard(models.Model):
    """
    ## Fields

    ### `id` (`integer`)
    Primary key.

    ### `person` (`integer`)
    Foreign key to the [CAMPUSonline person](../../campusonline/person) who owns
    this card. Name, photo, email and organization are read live from there.

    ### `has_apple_pass` (`boolean`)
    An Apple Wallet pass has been issued.

    ### `has_google_pass` (`boolean`)
    A Google Wallet pass has been issued.

    ### `created_at` (`datetime`)
    When the employee first opened their card page.

    ### `updated_at` (`datetime`)
    Last change to this card.
    """

    person = models.OneToOneField(
        "campusonline.Person", db_constraint=False, on_delete=models.DO_NOTHING
    )
    apple_pass_serial = models.CharField(
        max_length=100, blank=True, null=True, unique=True
    )
    google_pass_id = models.CharField(
        max_length=100, blank=True, null=True, unique=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Employee ID card")
        verbose_name_plural = _("Employee ID cards")
        permissions = (
            ("manage_passes", _("Can download and re-push any employee's passes")),
        )

    def __str__(self):
        return f"Employee ID Card {self.person_id}"

    @property
    def full_name(self):
        person = self.person
        prefix = _title_part(person.academic_title, "prefix")
        suffix = _title_part(person.academic_title, "suffix")
        name = " ".join(p for p in (prefix, person.first_name, person.last_name) if p)
        if suffix:
            name = f"{name}, {suffix}"
        return name

    @cached_property
    def organization(self):
        return self.person.organizations.first()

    @property
    def organization_name(self):
        return _localized(self.organization.name) if self.organization else ""

    # A row exists as soon as someone opens the page, so it does not mean a
    # pass was issued. These two do: the ids are set when a pass is generated.
    @property
    def has_apple_pass(self):
        return bool(self.apple_pass_serial)

    @property
    def has_google_pass(self):
        return bool(self.google_pass_id)

    def thumbnail(self, size):
        """The photo as a square, or the silhouette when there is none."""
        avatar = self.person.avatar_private
        if avatar:
            try:
                return utils.square(bytes(avatar), size)
            except (UnidentifiedImageError, OSError) as e:
                logger.error(
                    f"Could not process photo for employee {self.person_id}: {e}; using the silhouette."
                )
        return utils.silhouette(size)

    @translation.override("de")
    def apple_pass_json(self):
        if not self.apple_pass_serial:
            self.apple_pass_serial = str(uuid.uuid4())
            self.save()

        person = self.person
        org = self.organization

        pass_data = {
            "formatVersion": 1,
            "passTypeIdentifier": settings.IDCARD_APPLE_PASS_TYPE_ID,
            "serialNumber": self.apple_pass_serial,
            "teamIdentifier": settings.IDCARD_APPLE_TEAM_ID,
            "organizationName": "MedUni Graz",
            "description": f"MedUni Graz Employee ID - {self.full_name}",
            "backgroundColor": "rgb(0, 124, 49)",
            "foregroundColor": "rgb(255, 255, 255)",
            "labelColor": "rgb(255, 255, 255)",
            "generic": {
                "primaryFields": [
                    {"key": "name", "label": "NAME", "value": self.full_name}
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
            sec.append({"key": "oe_short", "label": "OE", "value": org.short})

        aux.append(
            {"key": "id", "label": "BEDIENSTETENNUMMER", "value": str(self.person_id)}
        )
        if person.email:
            aux.append({"key": "email", "label": "E-MAIL", "value": person.email})

        if self.organization_name:
            back.append(
                {
                    "key": "oe_full",
                    "label": "Organisationseinheit",
                    "value": self.organization_name,
                }
            )
        if org and org.address:
            back.append(
                {"key": "dienstort", "label": "Dienstort", "value": org.address}
            )
        if org and org.phone:
            back.append(
                {"key": "oe_phone", "label": "Telefon (OE)", "value": org.phone}
            )
        if org and org.email:
            back.append({"key": "oe_email", "label": "E-Mail (OE)", "value": org.email})

        if person.card:
            back.append(
                {"key": "visitenkarte", "label": "Visitenkarte", "value": person.card}
            )
            pass_data["barcodes"] = [
                {
                    "message": person.card,
                    "format": "PKBarcodeFormatQR",
                    "messageEncoding": "iso-8859-1",
                }
            ]

        back.append(
            {
                "key": "about",
                "label": "About",
                "value": "This card identifies you as an employee of the Medical University of Graz.",
            }
        )

        return pass_data

    def apple_pass(self, signed=True):
        """The .pkpass as bytes.

        With `signed=False` Wallet rejects the file, but it can still be
        unzipped and inspected.
        """
        files = {
            "pass.json": json.dumps(self.apple_pass_json(), indent=2).encode("utf-8")
        }
        files.update(utils.apple_images())
        # Apple fixes the thumbnail at 90x90pt, so 180x180 for the @2x variant.
        for size, name in ((90, "thumbnail.png"), (180, "thumbnail@2x.png")):
            buf = BytesIO()
            self.thumbnail(size).save(buf, format="PNG")
            files[name] = buf.getvalue()

        manifest = utils.apple_manifest(files)
        signature = utils.apple_sign(manifest) if signed else None

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as pkpass:
            for name, content in files.items():
                pkpass.writestr(name, content)
            pkpass.writestr("manifest.json", manifest)
            if signature:
                pkpass.writestr("signature", signature)
        return buf.getvalue()

    def google_private_image(self):
        """Upload the photo as a Google secure private image, returning its id or None.

        No public URL is ever created for it:
        https://developers.google.com/wallet/generic/use-cases/secure-private-images
        """
        avatar = self.person.avatar_private
        if not avatar:
            return None
        try:
            url = f"{utils.GOOGLE_PRIVATE_IMAGE_API}/{settings.IDCARD_GOOGLE_ISSUER_ID}/uploadPrivateImage"
            resp = utils.google_session().post(
                url, data=bytes(avatar), headers={"Content-Type": "image/jpeg"}
            )
            if resp.status_code not in (200, 201):
                logger.warning(
                    f"Private photo upload failed for employee {self.person_id}: {resp.status_code} {resp.text}"
                )
                return None
            return resp.json().get("privateImageId")
        except Exception as e:
            logger.error(
                f"Error uploading private photo for employee {self.person_id}: {e}"
            )
            return None

    @translation.override("de")
    def google_object(self):
        """The Generic pass object, mirroring the Apple field layout.

        Uploads the photo as a side effect when the employee has one.
        """
        issuer_id = settings.IDCARD_GOOGLE_ISSUER_ID

        if not self.google_pass_id:
            self.google_pass_id = f"{issuer_id}.{self.person_id}_{uuid.uuid4().hex[:8]}"
            self.save(update_fields=["google_pass_id"])

        person = self.person
        org = self.organization

        pass_object = {
            "id": self.google_pass_id,
            "classId": utils.google_class_id(),
            "genericType": "GENERIC_TYPE_UNSPECIFIED",
            # Phase B flips this to EXPIRED on revocation.
            "state": "ACTIVE",
            "hexBackgroundColor": utils.GOOGLE_BACKGROUND,
            "cardTitle": utils.google_localized("Medizinische Universität Graz"),
            "header": utils.google_localized(self.full_name),
            "textModulesData": [
                {
                    "id": "employee_id",
                    "header": "Bedienstetennummer",
                    "body": str(self.person_id),
                },
            ],
        }

        # Google fetches the logo from a public raster URL (PNG/JPG, not SVG),
        # so it is left out unless one is configured.
        if settings.IDCARD_GOOGLE_LOGO_URL:
            pass_object["logo"] = {
                "sourceUri": {"uri": settings.IDCARD_GOOGLE_LOGO_URL},
                "contentDescription": utils.google_localized(
                    "MedUni Graz Logo", "en-US"
                ),
            }

        private_image_id = self.google_private_image()
        if private_image_id:
            pass_object["imageModulesData"] = [
                {
                    "id": "photo",
                    "mainImage": {
                        "privateImageId": private_image_id,
                        "contentDescription": utils.google_localized(
                            f"Foto von {self.full_name}"
                        ),
                    },
                }
            ]

        if org and org.short:
            pass_object["subheader"] = utils.google_localized(org.short)

        text = pass_object["textModulesData"]
        if self.organization_name:
            text.append(
                {
                    "id": "org_unit",
                    "header": "Organisationseinheit",
                    "body": self.organization_name,
                }
            )
        if org and org.address:
            text.append({"id": "dienstort", "header": "Dienstort", "body": org.address})
        if person.email:
            text.append({"id": "email", "header": "E-Mail", "body": person.email})
        if org and org.phone:
            text.append({"id": "oe_phone", "header": "Telefon (OE)", "body": org.phone})
        if org and org.email:
            text.append({"id": "oe_email", "header": "E-Mail (OE)", "body": org.email})

        if person.card:
            pass_object["barcode"] = {"type": "QR_CODE", "value": person.card}
            pass_object["linksModuleData"] = {
                "uris": [
                    {
                        "uri": person.card,
                        "description": "Visitenkarte",
                        "id": "visitenkarte",
                    }
                ],
            }

        return pass_object

    def google_push(self):
        """Create or update this card's object at Google. Idempotent.

        Also the path for live updates and, in Phase B, revocation.
        """
        try:
            pass_object = self.google_object()
            session = utils.google_session()
            resp = session.post(
                f"{utils.GOOGLE_WALLET_API}/genericObject", json=pass_object
            )
            if resp.status_code == 409:
                resp = session.put(
                    f"{utils.GOOGLE_WALLET_API}/genericObject/{self.google_pass_id}",
                    json=pass_object,
                )
            if resp.status_code not in (200, 201):
                logger.warning(
                    f"Google Wallet object upsert returned {resp.status_code}: {resp.text}"
                )
                return False
            return True
        except Exception as e:
            logger.error(f"Error creating or updating the Google Wallet object: {e}")
            return False

    def google_save_url(self):
        """Push the class and object, then return a signed save link."""
        utils.google_upsert_class()
        if not self.google_push():
            # Signing a link to an object Google does not have would hand the
            # user an opaque Wallet error instead of ours. The upsert's
            # warning in the log carries Google's response.
            raise RuntimeError(
                f"Google Wallet object upsert failed for employee {self.person_id}; see the log for Google's response."
            )
        return utils.google_save_link(self.google_pass_id)
