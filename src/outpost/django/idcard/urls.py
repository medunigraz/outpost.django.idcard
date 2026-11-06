from django.urls import path

from . import views

app_name = "idcard"

urlpatterns = [
    path("my-pass/", views.MyPassView.as_view(), name="my-pass"),
    path("my-pass/apple/", views.ApplePassView.as_view(), name="apple-pass"),
    path("my-pass/google/", views.GooglePassView.as_view(), name="google-pass"),
    path("my-pass/phone/<str:token>/", views.HandoffView.as_view(), name="handoff"),
    path(
        "my-pass/phone/<str:token>/apple/",
        views.HandoffApplePassView.as_view(),
        name="handoff-apple",
    ),
    path(
        "my-pass/phone/<str:token>/google/",
        views.HandoffGooglePassView.as_view(),
        name="handoff-google",
    ),
    path(
        "wallet/v1/devices/<str:device>/registrations/<str:pass_type>/<str:serial>",
        views.AppleRegistrationView.as_view(),
        name="apple-registration",
    ),
    path(
        "wallet/v1/devices/<str:device>/registrations/<str:pass_type>",
        views.AppleSerialsView.as_view(),
        name="apple-serials",
    ),
    path(
        "wallet/v1/passes/<str:pass_type>/<str:serial>",
        views.AppleLatestPassView.as_view(),
        name="apple-latest-pass",
    ),
    path("wallet/v1/log", views.AppleLogView.as_view(), name="apple-log"),
]
