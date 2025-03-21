from django.urls import path

from . import views

app_name = "BabyUI"
urlpatterns = [path("aaa/", views.aaa), path("signin/", views.signin, name="signin"), path("", views.index), path("dashboard/", views.dashboard)]
