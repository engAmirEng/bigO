from django.urls import path

from . import views

app_name = "node_manager"
urlpatterns = [
    path("node/base-sync/", views.NodeBaseSyncAPIView.as_view(), name="node_base_sync"),
    path(
        "node/program-binary/hash/<str:hash>/content/",
        views.NodeProgramBinaryContentByHashAPIView.as_view(),
        name="node_program_binary_content_by_hash",
    ),
]
