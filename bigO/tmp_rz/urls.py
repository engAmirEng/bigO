from django.urls import path

from . import views

app_name = "tmp_rz"
urlpatterns = [
    path("core/tmp_rz1/", views.tmp_rz1),
    path("tmp_rz/tmp_rz2/", views.tmp_rz2),
]
