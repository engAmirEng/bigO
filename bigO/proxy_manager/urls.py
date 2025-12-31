from django.urls import path

from . import views

urlpatterns = [
    path("change-me/todo/<uuid:subscription_uuid>/", views.sublink_view),
    path("sub/<uuid:subscription_uuid>/", views.sublink_view),
]
