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
    path(
        "node/<int:node_id>/supervisor-api/path/",
        views.node_supervisor_server_proxy_view,
        name="node_supervisor_server_proxy_root_view",
    ),
    path(
        "node/<int:node_id>/supervisor-api/path/<path:path>",
        views.node_supervisor_server_proxy_view,
        name="node_supervisor_server_proxy_view",
    ),
    path("nginx-auth-request/", views.nginx_auth_request, name="nginx_auth_request"),
]
