from django.urls import path

from . import views

app_name = "BabyUI"
urlpatterns = [path("aaa/", views.aaa), path("", views.index), path("dashboard/", views.dashboard)]
