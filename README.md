# outpost.django.idcard

Digital employee ID cards for Medical University of Graz. Generates Apple Wallet and Google Wallet passes with employee information, photos, and QR codes.

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Access at http://localhost:8000/admin/

## Configuration

### Apple Wallet

Requires certificates from Apple Developer Account:
- Pass Type ID Certificate (`pass_certificate.pem`)
- Private Key (`pass_key.pem`)
- WWDR Certificate (`wwdr.pem`)

Place in `credentials/` directory and configure in settings.

### Google Wallet

1. Create project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Google Wallet API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download `google_oauth_client.json` to `credentials/`
5. Authenticate once:

```bash
python manage.py shell
>>> from outpost.django.idcard.google_pass import get_authenticated_credentials
>>> get_authenticated_credentials()
```

## Usage

**Manual**: Use Django admin to create employee cards

**SSO**: When deployed with outpost infrastructure, employees can generate passes via CAMPUSonline login at `/idcard/my-pass/`

## API Endpoints

- `/idcard/` - List employee cards
- `/idcard/employee/<id>/` - Card details
- `/idcard/api/employee/<id>/` - JSON API
- `/idcard/qr/<id>/` - QR code image
- `/idcard/apple-pass/<id>/` - Apple Wallet download
- `/idcard/google-pass/<id>/` - Google Wallet add

## License

BSD 2-Clause License - Medical University of Graz
