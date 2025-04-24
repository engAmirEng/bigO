from django.urls import path

from . import views

app_name = "node_manager"
urlpatterns = [
    path("node/base-sync/", views.NodeBaseSyncAPIView.as_view(), name="node_base_sync"),
    path("node/base-sync/v2/", views.node_base_sync_v2, name="node_base_sync_v2"),
    path(
        "node/program-binary/hash/<str:hash>/content/",
        views.NodeProgramBinaryContentByHashAPIView.as_view(),
        name="node_program_binary_content_by_hash",
    ),
    path(
        "node/<int:node_id>/<str:way>/supervisor-api/path/",
        views.node_supervisor_server_proxy_view,
        name="node_supervisor_server_proxy_root_view",
    ),
    path(
        "node/<int:node_id>/<str:way>/supervisor-api/path/<path:path>",
        views.node_supervisor_server_proxy_view,
        name="node_supervisor_server_proxy_view",
    ),
]
