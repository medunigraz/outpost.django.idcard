import base64
import io
import json
import logging
import re
from datetime import (
    datetime,
    timezone,
)

import qrcode
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core import signing
from django.db.models import Max
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.urls import reverse
from django.utils import translation
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.utils.html import escape
from django.utils.http import (
    http_date,
    parse_http_date_safe,
)
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.vary import vary_on_headers
from django.views.generic import (
    TemplateView,
    View,
)
from outpost.django.campusonline.models import Person

from . import (
    models,
    utils,
)
from .conf import settings

logger = logging.getLogger(__name__)

HANDOFF_SALT = "idcard.handoff"

_IOS_RE = re.compile(r"iPhone|iPad|iPod", re.IGNORECASE)
_ANDROID_RE = re.compile(r"Android", re.IGNORECASE)


def _detect_device(user_agent):
    if not user_agent:
        return "desktop"
    if _IOS_RE.search(user_agent):
        return "ios"
    if _ANDROID_RE.search(user_agent):
        return "android"
    return "desktop"


def _set_language_cookie(response, lang):
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        lang,
        max_age=settings.LANGUAGE_COOKIE_AGE,
        path=settings.LANGUAGE_COOKIE_PATH,
        domain=settings.LANGUAGE_COOKIE_DOMAIN,
        secure=settings.LANGUAGE_COOKIE_SECURE,
        httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
        samesite=settings.LANGUAGE_COOKIE_SAMESITE,
    )


def _qr_data_uri(text, box_size=8):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


class EmployeeCardMixin(LoginRequiredMixin):
    """The logged-in user's own card, created on first use. 404 unless employed."""

    def get_card(self):
        person = get_object_or_404(
            Person, username=self.request.user.username, employed=True
        )
        card, _ = models.EmployeeCard.objects.get_or_create(person=person)
        return card


class HandoffMixin:
    """The card a desktop page's QR code hands to a phone, without a login there.

    The signed token carries the card and expires after IDCARD_HANDOFF_MAX_AGE
    seconds, so a photographed code is useless soon after.
    """

    def dispatch(self, request, *args, **kwargs):
        try:
            pk = signing.loads(
                kwargs["token"],
                salt=HANDOFF_SALT,
                max_age=settings.IDCARD_HANDOFF_MAX_AGE,
            )
        except signing.BadSignature:
            with translation.override(translation.get_language_from_request(request)):
                return render(
                    request,
                    "idcard/error.html",
                    {
                        "error_message": _(
                            "This link has expired. Scan the QR code on your computer again."
                        )
                    },
                    status=410,
                )
        self.card = get_object_or_404(models.EmployeeCard, pk=pk, person__employed=True)
        return super().dispatch(request, *args, **kwargs)

    def get_card(self):
        return self.card


@method_decorator(vary_on_headers("User-Agent", "Accept-Language"), name="dispatch")
class MyPassView(LoginRequiredMixin, TemplateView):
    template_name = "idcard/my_pass_preview.html"

    def get(self, request, *args, **kwargs):
        lang = request.GET.get("lang")
        if lang in dict(settings.LANGUAGES):
            response = redirect("idcard:my-pass")
            _set_language_cookie(response, lang)
            return response

        # Outpost has no LocaleMiddleware, so scope the language to this
        # request, and render inside it rather than lazily after returning.
        with translation.override(translation.get_language_from_request(request)):
            try:
                person = Person.objects.get(username=request.user.username)
            except Person.DoesNotExist:
                return render(
                    request,
                    "idcard/error.html",
                    {
                        "error_title": "Person Not Found",
                        "error_message": f"No CAMPUSonline person record found for username: {request.user.username}",
                    },
                )

            if not person.employed:
                return render(
                    request,
                    "idcard/error.html",
                    {
                        "error_title": "Not Eligible",
                        "error_message": "Digital ID cards are only available to currently-employed staff.",
                    },
                )

            card, _ = models.EmployeeCard.objects.get_or_create(person=person)
            return self.render_to_response(
                self.get_context_data(employee_card=card, person=person)
            ).render()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        device = _detect_device(self.request.META.get("HTTP_USER_AGENT", ""))
        context["device"] = device
        context["apple_url"] = reverse("idcard:apple-pass")
        context["google_url"] = reverse("idcard:google-pass")
        if device == "desktop":
            token = signing.dumps(kwargs["employee_card"].pk, salt=HANDOFF_SALT)
            handoff = reverse("idcard:handoff", args=[token])
            context["qr_data_uri"] = _qr_data_uri(
                self.request.build_absolute_uri(handoff)
            )
            context["handoff_minutes"] = settings.IDCARD_HANDOFF_MAX_AGE // 60
        return context


@method_decorator(vary_on_headers("User-Agent", "Accept-Language"), name="dispatch")
class HandoffView(HandoffMixin, TemplateView):
    """The card page on the phone, opened from the desktop QR code."""

    template_name = "idcard/my_pass_preview.html"

    def get(self, request, token):
        with translation.override(translation.get_language_from_request(request)):
            return self.render_to_response(
                {
                    "employee_card": self.card,
                    "person": self.card.person,
                    "device": _detect_device(request.META.get("HTTP_USER_AGENT", "")),
                    "apple_url": reverse("idcard:handoff-apple", args=[token]),
                    "google_url": reverse("idcard:handoff-google", args=[token]),
                }
            ).render()


class ApplePass(View):
    """Serves get_card()'s .pkpass; the subclass decides whose card that is."""

    def get(self, request, *args, **kwargs):
        card = self.get_card()
        try:
            data = card.apple_pass()
        except Exception as e:
            logger.exception(
                f"Apple Wallet pass generation failed for employee {card.person_id}"
            )
            return HttpResponse(
                "<h1>Error generating pass</h1>"
                f"<p>{escape(str(e))}</p>"
                "<p>Check that:</p>"
                "<ul>"
                "<li>IDCARD_APPLE_CERTIFICATE, IDCARD_APPLE_KEY and IDCARD_APPLE_WWDR_CERTIFICATE hold the PEM text</li>"
                "<li>IDCARD_APPLE_KEY_PASSWORD matches the key, or is unset for an unencrypted key</li>"
                "</ul>",
                status=500,
            )
        response = HttpResponse(data, content_type="application/vnd.apple.pkpass")
        response["Content-Disposition"] = (
            f'attachment; filename="meduni_id_{card.person_id}.pkpass"'
        )
        return response


class ApplePassView(EmployeeCardMixin, ApplePass):
    pass


class HandoffApplePassView(HandoffMixin, ApplePass):
    pass


class GooglePass(View):
    """Redirects to get_card()'s save link; the subclass decides whose card that is."""

    def get(self, request, *args, **kwargs):
        missing = utils.google_missing_settings()
        if missing:
            return HttpResponse(
                "<h1>Google Wallet Not Configured</h1>"
                f"<p>Unset in your Django settings: <code>{escape(', '.join(missing))}</code>.</p>"
                "<p>See the Settings section of the idcard README.</p>",
                status=503,
            )

        card = self.get_card()
        try:
            save_url = card.google_save_url()
        except Exception as e:
            logger.exception(
                f"Google Wallet pass generation failed for employee {card.person_id}"
            )
            return HttpResponse(
                "<h1>Error Generating Google Wallet Pass</h1>"
                f"<p>{escape(str(e))}</p>"
                "<p>Check that:</p><ul>"
                "<li>IDCARD_GOOGLE_ISSUER_ID matches the Business Console</li>"
                "<li>IDCARD_GOOGLE_SERVICE_ACCOUNT holds the service-account key as a dict</li>"
                "<li>The service account is added to the issuer (Developer access)</li>"
                "<li>The Google Wallet API is enabled on the Cloud project</li>"
                "</ul>",
                status=500,
            )
        return HttpResponseRedirect(save_url)


class GooglePassView(EmployeeCardMixin, GooglePass):
    pass


class HandoffGooglePassView(HandoffMixin, GooglePass):
    pass


# Apple's pass web service, called by Wallet itself:
# https://developer.apple.com/documentation/walletpasses/adding-a-web-service-to-update-passes


def _apple_card(request, pass_type, serial):
    """The card Wallet asks about, or None when its token does not match."""
    if pass_type != settings.IDCARD_APPLE_PASS_TYPE_ID:
        raise Http404
    card = get_object_or_404(models.EmployeeCard, apple_pass_serial=serial)
    auth = request.headers.get("Authorization", "")
    if card.apple_auth_token and constant_time_compare(
        auth, f"ApplePass {card.apple_auth_token}"
    ):
        return card
    return None


@method_decorator(csrf_exempt, name="dispatch")
class AppleRegistrationView(View):
    def post(self, request, device, pass_type, serial):
        card = _apple_card(request, pass_type, serial)
        if card is None:
            return HttpResponse(status=401)
        try:
            push_token = json.loads(request.body)["pushToken"]
        except (ValueError, KeyError, TypeError):
            return HttpResponse(status=400)
        _, created = models.AppleRegistration.objects.update_or_create(
            card=card, device=device, defaults={"push_token": push_token}
        )
        return HttpResponse(status=201 if created else 200)

    def delete(self, request, device, pass_type, serial):
        card = _apple_card(request, pass_type, serial)
        if card is None:
            return HttpResponse(status=401)
        card.apple_registrations.filter(device=device).delete()
        return HttpResponse(status=200)


class AppleSerialsView(View):
    """Serials of this device's passes changed since Wallet's last check."""

    def get(self, request, device, pass_type):
        if pass_type != settings.IDCARD_APPLE_PASS_TYPE_ID:
            raise Http404
        cards = models.EmployeeCard.objects.filter(apple_registrations__device=device)
        try:
            since = float(request.GET["passesUpdatedSince"])
        except (KeyError, ValueError):
            since = None
        if since is not None:
            cards = cards.filter(
                pass_updated_at__gt=datetime.fromtimestamp(since, tz=timezone.utc)
            )
        serials = list(cards.values_list("apple_pass_serial", flat=True))
        if not serials:
            return HttpResponse(status=204)
        last = cards.aggregate(Max("pass_updated_at"))["pass_updated_at__max"]
        last = last or datetime.now(tz=timezone.utc)
        # A plain number, so the tag survives Wallet putting it in a query string.
        return JsonResponse(
            {"serialNumbers": serials, "lastUpdated": str(last.timestamp())}
        )


class AppleLatestPassView(View):
    def get(self, request, pass_type, serial):
        card = _apple_card(request, pass_type, serial)
        if card is None:
            return HttpResponse(status=401)
        modified = int((card.pass_updated_at or card.created_at).timestamp())
        since = parse_http_date_safe(request.headers.get("If-Modified-Since", ""))
        if since and modified <= since:
            return HttpResponse(status=304)
        response = HttpResponse(
            card.apple_pass(), content_type="application/vnd.apple.pkpass"
        )
        response["Last-Modified"] = http_date(modified)
        return response


@method_decorator(csrf_exempt, name="dispatch")
class AppleLogView(View):
    """Wallet reports web service errors here. Unauthenticated, so capped."""

    def post(self, request):
        try:
            logs = json.loads(request.body).get("logs", [])
        except (ValueError, AttributeError):
            logs = []
        for line in logs[:20]:
            logger.warning(f"Apple Wallet: {str(line)[:500]}")
        return HttpResponse(status=200)
