from appconf import AppConf
from django.conf import settings


class IDCardAppConf(AppConf):
    APPLE_PASS_TYPE_ID = "pass.at.medunigraz.idcard"
    APPLE_TEAM_ID = "A4T23767YU"
    APPLE_CERTIFICATE = None
    APPLE_KEY = None
    APPLE_KEY_PASSWORD = None
    APPLE_WWDR_CERTIFICATE = None
    GOOGLE_ISSUER_ID = "3388000000023162641"
    GOOGLE_SERVICE_ACCOUNT = None
    GOOGLE_LOGO_URL = ""

    class Meta:
        prefix = "idcard"
