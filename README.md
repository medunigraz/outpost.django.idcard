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

`EmployeeCard` holds one row per employee who has opened their card page,
linked one-to-one to their CAMPUSonline `Person`, whose id is the
Bedienstetennummer. It stores only pass metadata; names, organisation and
photo are read live from `Person` whenever a pass is built. Only employees are
eligible; `Person.employed` is the single gate.

Employees can reach only their own card. Other people's cards are visible only
in the admin and the API, to holders of `idcard.view_employeecard`. Photos come from
`Person.avatar_private`, served through campusonline's `PrivateAvatarView`,
never CAMPUSonline's public avatar URL.

Not built yet: pushing updates to an Apple pass already on a phone, and marking
a pass expired when someone leaves. Google passes can already be re-pushed, see
Tasks. Neither Apple nor Google
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

`outpost.django.campusonline` must be installed: all employee data comes from
its `Person` model.

### Trying it out without any credentials

Most of the app needs no secrets. Signed in as anyone with a CAMPUSonline
`Person` record whose `employed` is true, `/idcard/my-pass/` will look you up,
create your `EmployeeCard` row and render the page with your CAMPUSonline
photo and both wallet buttons. That exercises the model, the migrations,
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

Declared in `conf.py` with the `IDCARD_` prefix. Set them in the deployment's
configuration file. Keys and certificates go in as their PEM text, not as
paths.

| Setting | What | Default |
|---|---|---|
| `IDCARD_APPLE_PASS_TYPE_ID` | Pass Type identifier | `pass.at.medunigraz.idcard` |
| `IDCARD_APPLE_TEAM_ID` | Apple Developer team identifier | `A4T23767YU` |
| `IDCARD_APPLE_CERTIFICATE` | Pass Type ID certificate, PEM | required |
| `IDCARD_APPLE_KEY` | Its private key, PEM | required |
| `IDCARD_APPLE_KEY_PASSWORD` | Key password, if the key is encrypted | `None` |
| `IDCARD_APPLE_WWDR_CERTIFICATE` | Apple WWDR intermediate certificate, PEM | required |
| `IDCARD_GOOGLE_ISSUER_ID` | Numeric issuer ID from the Business Console | `3388000000023162641` |
| `IDCARD_GOOGLE_SERVICE_ACCOUNT` | The service-account JSON key, as a dict | required |
| `IDCARD_GOOGLE_LOGO_URL` | Public raster logo URL for Google | empty |

The service account's `client_email` must be granted access to the issuer in
the Wallet Business Console. The same key both authorises the REST calls and
signs the save link, which is why user OAuth will not do — it cannot run
headless.

`IDCARD_GOOGLE_LOGO_URL` must be a **public** raster URL (PNG/JPG, not SVG)
because Google fetches it. Leave it empty in development; Google substitutes a
generated letter monogram.

## URLs

| Path | Purpose | Who |
|---|---|---|
| `/idcard/my-pass/` | The employee's own card | Any employee |
| `/idcard/my-pass/apple/` | Download their own `.pkpass` | Any employee |
| `/idcard/my-pass/google/` | Redirect to their own Google save link | Any employee |
| `/v1/idcard/card/` | Cards as JSON, `?expand=person` for the CAMPUSonline data | Own card; all with `idcard.view_employeecard` |

All cards are listed in the Django admin. Its actions "Download Apple pass" and
"Re-push Google pass" need the `idcard.manage_passes` permission, which an
admin grants to a hand-made group.

## Tasks

| Task | What |
|---|---|
| `outpost.django.idcard.tasks.Card:google_push` | Push one card's current data to Google |
| `outpost.django.idcard.tasks.Card:synchronize` | Push every card that has a Google pass |

Schedule `Card:synchronize` with a periodic task in the admin to keep Google
passes current.

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
