from django.contrib import (
    admin,
    messages,
)
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from outpost.django.base.admin import ReadOnlyAdminMixin

from . import (
    models,
    tasks,
)


@admin.register(models.EmployeeCard)
class EmployeeCardAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "person_id",
        "full_name",
        "has_photo",
        "has_apple_pass",
        "has_google_pass",
        "created_at",
    )
    list_select_related = ("person",)
    search_fields = (
        "=person__id",
        "person__first_name",
        "person__last_name",
        "person__username",
    )
    list_filter = (
        "created_at",
        ("apple_pass_serial", admin.EmptyFieldListFilter),
        ("google_pass_id", admin.EmptyFieldListFilter),
    )
    fieldsets = (
        (None, {"fields": ("person",)}),
        (
            _("Pass metadata"),
            {
                "fields": ("apple_pass_serial", "google_pass_id"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
    actions = ("apple_pass", "google_push")

    def has_manage_passes_permission(self, request):
        """Does the user have the manage_passes permission?"""
        return request.user.has_perm(f"{self.opts.app_label}.manage_passes")

    def full_name(self, obj):
        return obj.full_name

    full_name.short_description = _("Name")

    def has_photo(self, obj):
        return bool(obj.person.hash)

    has_photo.boolean = True
    has_photo.short_description = _("Photo")

    def has_apple_pass(self, obj):
        return obj.has_apple_pass

    has_apple_pass.boolean = True
    has_apple_pass.short_description = _("Apple")

    def has_google_pass(self, obj):
        return obj.has_google_pass

    has_google_pass.boolean = True
    has_google_pass.short_description = _("Google")

    def apple_pass(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                _("Select exactly one card to download its Apple pass."),
                messages.WARNING,
            )
            return
        card = queryset.get()
        response = HttpResponse(
            card.apple_pass(), content_type="application/vnd.apple.pkpass"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="meduni_id_{card.person_id}.pkpass"'
        )
        return response

    apple_pass.short_description = _("Download Apple pass")
    apple_pass.allowed_permissions = ("manage_passes",)

    def google_push(self, request, queryset):
        cards = queryset.exclude(google_pass_id=None)
        for card in cards:
            tasks.CardTasks().google_push.apply_async((card.pk,), queue="maintenance")
        self.message_user(
            request,
            _(
                "%i queued for pushing to Google. Cards without a Google pass were skipped."
            )
            % cards.count(),
        )

    google_push.short_description = _("Re-push Google pass")
    google_push.allowed_permissions = ("manage_passes",)
