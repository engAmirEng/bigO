from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("nginx-flower-auth-request/", views.nginx_flower_auth_request, name="nginx_flower_auth_request"),
    path("tmp_rz1/", views.tmp_rz1),
]
