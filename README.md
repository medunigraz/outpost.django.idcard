# outpost.django.idcard

Digital employee ID cards for the Medical University of Graz, as Apple Wallet
and Google Wallet passes.

An employee signs in at `/idcard/my-pass/` and adds their card to their phone.
The card shows their name, Bedienstetennummer, organisational unit and contact
details, pulled live from CAMPUSonline, plus a QR code to their Visitenkarte.
It is a visual card only. Nothing scans or verifies it.

Installs into the wider `outpost` project, and depends on
`outpost.django.campusonline` for employee data.

## Data and access

`EmployeeCard` holds one row per employee who has requested a card, keyed by
`employee_id` (which is `Person.id`). It is a denormalised snapshot of the
CAMPUSonline record, refreshed whenever the employee opens their card page.
Only employees are eligible; `Person.employed` is the single gate.

Employees can reach only their own card. Anything exposing another person is
restricted to staff via the Django `is_staff` flag. Photos are served only
through authenticated views, never `MEDIA_URL` and never CAMPUSonline's public
avatar URL.

Not built yet: pushing updates to a pass already on a phone, and marking a pass
expired when someone leaves. Both are one nightly job. Neither Apple nor Google
can delete a pass off a phone, so revocation means showing it as expired.

## Install

```bash
pip install -e .
```

Add to `INSTALLED_APPS`. URLs mount at `/idcard/`.

## Settings

```python
APPLE_PASS_TYPE_ID          GOOGLE_WALLET_ISSUER_ID
APPLE_TEAM_ID               GOOGLE_SERVICE_ACCOUNT_FILE
APPLE_PASS_CERT_PATH        GOOGLE_WALLET_LOGO_URL
APPLE_PASS_KEY_PATH
APPLE_WWDR_PATH
APPLE_PASS_CERTIFICATE_PASSWORD
```

Apple needs a Pass Type ID certificate, its key, and the WWDR certificate.

Google needs a service-account JSON key and the numeric issuer ID, with the
service account's `client_email` granted access to the issuer in the Wallet
Business Console. The same key authorises the REST calls and signs the save
link, which is why user OAuth will not do. `GOOGLE_WALLET_LOGO_URL` is
optional, and must be a public raster URL if set.

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
inspecting someone else's pass. Without `outpost.django.campusonline`,
`/my-pass/` returns 503.

## Other

Generate a signed `.pkpass` on disk, to hand someone a card directly:

```bash
python -m django generate_idcard_file <username>
python -m django generate_idcard_file --search <surname>
```

German is the primary language, English the fallback, in
`locale/de/LC_MESSAGES/`. The compiled `django.mo` is committed because
deployment has no build step. Run `compilemessages -l de` after editing the
`.po`.

## License

BSD 2-Clause, Medical University of Graz.
