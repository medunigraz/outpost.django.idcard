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

Add `outpost.django.idcard` to `INSTALLED_APPS`, then:

```bash
python -m django migrate idcard
```

URLs mount at `/idcard/` through the usual `outpost.django.urls` discovery.
There is no `endpoints.py`; this app is HTML only, nothing on `/v1/`.

`outpost.django.campusonline` must be installed — all employee data comes from
its `Person` model. Without it `/idcard/my-pass/` returns 503 rather than
failing at import.

### Trying it out without any credentials

Most of the app needs no secrets. Signed in as anyone with a CAMPUSonline
`Person` record whose `employed` is true, `/idcard/my-pass/` will look you up,
create your `EmployeeCard` row, pull your photo out of CAMPUSonline and render
the page with both wallet buttons. That exercises the model, the migrations,
the CAMPUSonline integration, the photo handling and the access rules.

Only the two buttons themselves need credentials — the Apple certificate trio
to sign a `.pkpass`, and the Google service-account key to sign a save link.
With the settings below unset, both routes return a "not configured" page
naming what is missing, rather than an error.

One thing worth knowing before testing the Google button: the issuer is still
in demo mode, so **only accounts holding Admin or Developer on the issuer, or
explicitly added as test accounts in the Wallet Business Console, can save a
pass at all**. A save that fails for anyone else is that, not a bug.

## Settings

Required for Apple `.pkpass` generation:

| Setting | What |
|---|---|
| `APPLE_PASS_TYPE_ID` | Pass Type identifier, e.g. `pass.at.medunigraz.idcard` |
| `APPLE_TEAM_ID` | Apple Developer team identifier |
| `APPLE_PASS_CERT_PATH` | Pass Type ID certificate, PEM |
| `APPLE_PASS_KEY_PATH` | Its private key, PEM |
| `APPLE_WWDR_PATH` | Apple WWDR intermediate certificate, PEM |
| `APPLE_PASS_CERTIFICATE_PASSWORD` | Key password, empty string if none |

Signing shells out to `openssl`, so the binary must be on PATH.

Required for Google Wallet:

| Setting | What |
|---|---|
| `GOOGLE_WALLET_ISSUER_ID` | Numeric issuer ID from the Business Console |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Path to the service-account JSON key |

The service account's `client_email` must be granted access to the issuer in
the Wallet Business Console. The same key both authorises the REST calls and
signs the save link, which is why user OAuth will not do — it cannot run
headless.

Optional: `GOOGLE_WALLET_LOGO_URL`, which must be a **public** raster URL
(PNG/JPG, not SVG) because Google fetches it. Leave it empty in development;
Google substitutes a generated letter monogram.

`MEDIA_ROOT` and `MEDIA_URL` must be set, since stored photos are written
through Django's file storage. Photos are only ever served through the
authenticated views, never linked via `MEDIA_URL`.

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
