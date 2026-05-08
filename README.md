# outpost.django.idcard

Digital employee ID cards (Apple Wallet + Google Wallet) for the Medical
University of Graz. Designed to be installed into the wider `outpost` Django
project; depends on `outpost.django.campusonline` for employee data.

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
GOOGLE_OAUTH_CLIENT_FILE
GOOGLE_WALLET_TOKEN_FILE
GOOGLE_WALLET_LOGO_URL
```

Apple needs a Pass Type ID certificate, key, and the WWDR cert. Google needs an
OAuth 2.0 Desktop client + Wallet Issuer ID; the token file is created on first
auth.

## URLs

| Path                          | Purpose                              |
|-------------------------------|--------------------------------------|
| `/idcard/`                    | Card list (admin)                    |
| `/idcard/employee/<id>/`      | Card detail (admin)                  |
| `/idcard/apple-pass/<id>/`    | Download `.pkpass`                   |
| `/idcard/google-pass/<id>/`   | Add-to-Google-Wallet page            |
| `/idcard/my-pass/`            | SSO: logged-in employee's own card   |

`/my-pass/` requires `outpost.django.campusonline`; otherwise returns 503.

## License

BSD 2-Clause — Medical University of Graz.
