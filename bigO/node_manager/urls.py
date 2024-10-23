from django.urls import path

from . import views

app_name = "node_manager"
urlpatterns = [
    path("node/sync-me/", views.NodeSyncMeAPIView.as_view(), name="node_sync_me"),
]
