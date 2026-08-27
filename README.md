# outpost.django.idcard

Digital employee ID cards (Apple Wallet + Google Wallet) for the Medical
University of Graz. Designed to be installed into the wider `outpost` Django
project; depends on `outpost.django.campusonline` for employee data.

An employee signs in, opens `/idcard/my-pass/`, and adds their card to their
phone. The card shows live CAMPUSonline data (name, Bedienstetennummer,
organisational unit, contact) and a QR code linking to their Visitenkarte.
The card is **visual only** — nothing scans or verifies it.

## What it maintains

`EmployeeCard` is a denormalised snapshot of the CAMPUSonline `Person` record,
keyed by `employee_id` (= `Person.id`). One row per employee who has requested
a card. The intended lifecycle:

| Event | Effect on the card |
|---|---|
| Employee opens `/idcard/my-pass/` | Row is created (or refreshed) and their photo fetched — ✅ implemented |
| Their CAMPUSonline details change | Pass already on the phone updates automatically — ⏳ not yet implemented |
| They leave (`Person.employed` becomes false) | Pass is marked expired/voided on both platforms — ⏳ not yet implemented |

The last two are one mechanism, not two: a nightly reconcile job compares each
issued card against CAMPUSonline and pushes changes to the device (Apple
PassKit web service + APNs; Google object PATCH). Neither platform can force a
pass off a phone — revocation means the live card shows as **expired**.

Only employees are eligible; `Person.employed` is the single gate.

## Access control

Employees can only ever reach **their own** card. Everything that exposes
another person's data is restricted to staff — the handful of developers and
administrators who maintain the system, controlled by the Django `is_staff`
flag (User → *Staff status* in the admin).

Photos are served exclusively through authenticated views. They are never
linked via `MEDIA_URL`, which is unauthenticated, and never via CAMPUSonline's
public avatar URL — that URL returns HTML rather than an image for staff who
marked their photo internal-only.

## Install

```bash
pip install -e .
```

Add to `INSTALLED_APPS`. URLs auto-mount at `/idcard/`.

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

Apple needs a Pass Type ID certificate, key, and the WWDR cert.

Google needs a **service-account** JSON key and the numeric Wallet Issuer ID.
The service account's `client_email` must be granted access to the issuer in
the Google Wallet Business Console. The same private key both authorises the
REST calls and signs the "Add to Google Wallet" link, which is why a
service account is required rather than a user OAuth flow.

`GOOGLE_WALLET_LOGO_URL` is optional and must be a **public** raster URL if
set — Google's servers fetch it. Leave it empty when no such URL exists.

## URLs

| Path | Purpose | Who |
|---|---|---|
| `/idcard/my-pass/` | The employee's own card | Any signed-in employee |
| `/idcard/my-pass/generate/` | Download their `.pkpass` | Any signed-in employee |
| `/idcard/my-pass/photo/` | Their own photo (takes no id) | Any signed-in employee |
| `/idcard/google-pass/<id>/` | Redirect to the signed Google save link | Owner, or staff |
| `/idcard/employee/<id>/photo/` | An employee's photo | Owner, or staff |
| `/idcard/` | Card list | Staff |
| `/idcard/employee/<id>/` | Card detail | Staff |
| `/idcard/api/employee/<id>/` | Card as JSON | Staff |
| `/idcard/qr/<id>/` | QR code image | Staff |
| `/idcard/apple-pass/<id>/` | Download any employee's `.pkpass` | Staff |
| `/idcard/apple-pass-preview/<id>/` | Pass preview page | Staff |

`/my-pass/` requires `outpost.django.campusonline`; otherwise returns 503.

Adding `?preview=1` to `/idcard/google-pass/<id>/` renders an interstitial
page instead of redirecting. Staff only — it exists for inspecting someone
else's pass.

## Translations

German is the primary language, English the fallback. Translations live in
`locale/de/LC_MESSAGES/`. The compiled `django.mo` is committed deliberately:
deployment is a git checkout plus an editable install with no build step, so
an uncompiled catalogue would silently fall back to English everywhere.

After editing `django.po`, recompile it:

```bash
python3 -m django compilemessages -l de
```

## License

BSD 2-Clause — Medical University of Graz.
