from django.urls import path

from . import views

sublink_view_path = path("<path:sublink_path>/", views.dynamic_sublink_view)
