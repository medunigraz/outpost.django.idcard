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

A card is revoked when its person is no longer employed or has dropped out of
CAMPUSonline, or by hand in the admin. Neither Apple nor Google can delete a
pass off a phone, so revocation means showing it as expired: Google sets the
object to `EXPIRED`, Apple serves the pass `voided`. The nightly
`Card:synchronize` revokes and pushes changed passes to both platforms.

Apple passes only update when they carry `webServiceURL`, which is fixed into
each pass when it is signed. Passes issued without `IDCARD_APPLE_WEB_SERVICE_URL`,
or for a host that later goes away, can never be updated or revoked.

## Install

```bash
pip install -e .
```

Add `outpost.django.idcard` to `INSTALLED_APPS`, then:

```bash
python -m django migrate idcard
```

URLs mount at `/idcard/` through the usual `outpost.django.urls` discovery,
the API at `/v1/idcard/` through `endpoints.py`.

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
| `IDCARD_APPLE_WEB_SERVICE_URL` | Base of the pass web service, e.g. `https://api-test.medunigraz.at/idcard/wallet` (HTTPS, no trailing slash) | `None`, passes cannot update |
| `IDCARD_GOOGLE_ISSUER_ID` | Numeric issuer ID from the Business Console | `3388000000023162641` |
| `IDCARD_GOOGLE_SERVICE_ACCOUNT` | The service-account JSON key, as a dict | required |
| `IDCARD_GOOGLE_IMAGE_URL` | Public URL of this app's static `idcard/` folder, e.g. `https://api-test.medunigraz.at/static/idcard/` | empty |

The service account's `client_email` must be granted access to the issuer in
the Wallet Business Console. The same key both authorises the REST calls and
signs the save link, which is why user OAuth will not do — it cannot run
headless.

Google fetches the logo, wide logo, banner and no-photo silhouette itself from
`IDCARD_GOOGLE_IMAGE_URL`, so that folder must be reachable without login
(`collectstatic` puts the files there). Leave it empty in development; the pass
then has no logo, banner or silhouette. Employee photos never go through it: they
are uploaded as private images.

## URLs

| Path | Purpose | Who |
|---|---|---|
| `/idcard/my-pass/` | The employee's own card | Any employee |
| `/idcard/my-pass/apple/` | Download their own `.pkpass` | Any employee |
| `/idcard/my-pass/google/` | Redirect to their own Google save link | Any employee |
| `/idcard/wallet/v1/...` | Apple pass web service (register, unregister, changed serials, latest pass, log) | Apple Wallet, authenticated per pass |
| `/v1/idcard/card/` | Cards as JSON, `?expand=person` for the CAMPUSonline data | Own card; all with `idcard.view_employeecard` |

All cards are listed in the Django admin. Its actions "Download Apple pass",
"Re-push Google pass", "Revoke card" and "Reactivate card" need the
`idcard.manage_passes` permission, which an admin grants to a hand-made group.
Revoke and reactivate run immediately, without a Celery worker. A card whose
person is not employed stays revoked.

## Tasks

| Task | What |
|---|---|
| `outpost.django.idcard.tasks.Card:google_push` | Push one card's current data to Google |
| `outpost.django.idcard.tasks.Card:synchronize` | Revoke cards of people no longer employed, push every card whose content changed to Google and Apple |

"Re-push Google pass" queues `Card:google_push` on the `maintainance` queue,
so a worker must consume it. Schedule `Card:synchronize` nightly with a
periodic task in the admin. Apple
pushes go to the APNs production environment with the Pass Type ID certificate,
so the server needs outbound HTTPS to `api.push.apple.com`.

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
