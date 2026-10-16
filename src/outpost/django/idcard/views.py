import base64
import io
import logging
import re

import qrcode
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import (
    HttpResponse,
    HttpResponseRedirect,
)
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.urls import reverse
from django.utils import translation
from django.utils.decorators import method_decorator
from django.utils.html import escape
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
    img = qr.make_image(fill_color="#007c31", back_color="white")
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
        page_url = self.request.build_absolute_uri(reverse("idcard:my-pass"))
        context["device"] = device
        context["qr_data_uri"] = _qr_data_uri(page_url) if device == "desktop" else None
        return context


class ApplePassView(EmployeeCardMixin, View):
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


class GooglePassView(EmployeeCardMixin, View):
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
