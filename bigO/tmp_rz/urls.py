from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("core/tmp_rz1/", views.tmp_rz1),
]
