# outpost.django.idcard

Digital employee ID cards for the Medical University of Graz, as Apple Wallet
and Google Wallet passes.

An employee signs in at `/idcard/my-pass/` and adds their card to their phone.
The card shows their name, Bedienstetennummer, organisational unit and contact
details, pulled live from CAMPUSonline, plus a QR code linking to their
Visitenkarte. It is a visual card only. Nothing scans or verifies it.

Installs into the wider `outpost` Django project and depends on
`outpost.django.campusonline` for employee data.

## Data

`EmployeeCard` holds one row per employee who has requested a card. It is a
denormalised snapshot of the CAMPUSonline `Person` record, keyed by
`employee_id` (which is `Person.id`). The row is created or refreshed whenever
the employee opens their card page.

Only employees are eligible. `Person.employed` is the single gate.

Two things are planned but not built yet: pushing updates to a pass already on
a phone when someone's details change, and marking a pass expired when someone
leaves. Both are the same mechanism, a nightly job that compares each card
against CAMPUSonline and pushes changes to the device. Note that neither Apple
nor Google can delete a pass off a phone, so revocation means the card shows as
expired.

## Access

Employees can only reach their own card. Everything that exposes another
person's data is restricted to staff, meaning the developers and admins who
maintain the system, via the Django `is_staff` flag.

Photos are served only through authenticated views, never through `MEDIA_URL`
(which has no authentication) and never through CAMPUSonline's public avatar
URL (which returns HTML rather than an image for staff who keep their photo
internal).

## Install

```bash
pip install -e .
```

Add to `INSTALLED_APPS`. URLs mount at `/idcard/`.

## Settings

```python
APPLE_PASS_TYPE_ID
APPLE_TEAM_ID
APPLE_PASS_CERT_PATH
APPLE_PASS_KEY_PATH
APPLE_WWDR_PATH
APPLE_PASS_CERTIFICATE_PASSWORD

GOOGLE_WALLET_ISSUER_ID
GOOGLE_SERVICE_ACCOUNT_FILE
GOOGLE_WALLET_LOGO_URL
```

Apple needs a Pass Type ID certificate, its key, and the WWDR certificate.

Google needs a service-account JSON key and the numeric Wallet Issuer ID. The
service account's `client_email` must have access to the issuer in the Wallet
Business Console. The same key both authorises the REST calls and signs the
save link, which is why a service account is required rather than user OAuth.

`GOOGLE_WALLET_LOGO_URL` is optional. If set it must be a public raster URL,
since Google's servers fetch it. Leave it empty when there isn't one.

## URLs

| Path | Purpose | Who |
|---|---|---|
| `/idcard/my-pass/` | The employee's own card | Any employee |
| `/idcard/my-pass/generate/` | Download their `.pkpass` | Any employee |
| `/idcard/my-pass/photo/` | Their own photo, takes no id | Any employee |
| `/idcard/google-pass/<id>/` | Redirect to the Google save link | Owner or staff |
| `/idcard/employee/<id>/photo/` | An employee's photo | Owner or staff |
| `/idcard/` | Card list | Staff |
| `/idcard/employee/<id>/` | Card detail | Staff |
| `/idcard/api/employee/<id>/` | Card as JSON | Staff |
| `/idcard/qr/<id>/` | QR code image | Staff |
| `/idcard/apple-pass/<id>/` | Any employee's `.pkpass` | Staff |
| `/idcard/apple-pass-preview/<id>/` | Pass preview page | Staff |

`?preview=1` on the Google URL renders a page instead of redirecting, for
inspecting someone else's pass. Staff only.

Without `outpost.django.campusonline`, `/my-pass/` returns 503.

## Management command

Generate a signed `.pkpass` on disk, for handing someone a card directly:

```bash
python -m django generate_idcard_file <username>
python -m django generate_idcard_file --search <surname>
```

## Translations

German is primary, English the fallback, in `locale/de/LC_MESSAGES/`. The
compiled `django.mo` is committed on purpose: deployment is a checkout plus an
editable install with no build step, so an uncompiled catalogue would silently
fall back to English. After editing the `.po`:

```bash
python -m django compilemessages -l de
```

## License

BSD 2-Clause, Medical University of Graz.
