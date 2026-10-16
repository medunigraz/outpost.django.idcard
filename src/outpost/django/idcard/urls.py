from django.urls import path

from . import views

app_name = "idcard"

urlpatterns = [
    path("my-pass/", views.MyPassView.as_view(), name="my-pass"),
    path("my-pass/apple/", views.ApplePassView.as_view(), name="apple-pass"),
    path("my-pass/google/", views.GooglePassView.as_view(), name="google-pass"),
]
