from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

import bigO.proxy_manager.urls
from bigO.graphql.schema import schema
from bigO.graphql.views import GraphQLView
from bigO.utils.decorators import csrf_exempt
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),
    # Telegram webhook handler
    # path("", include(bigO.telegram_bot.urls)),
    # local apps
    path("core/", include("bigO.core.urls")),
    path("node-manager/", include("bigO.node_manager.urls")),
    path("BabyUI/", include("bigO.BabyUI.urls")),
    path("", include("bigO.tmp_rz.urls")),
    # Graphql url
    path("graphql/", csrf_exempt(GraphQLView.as_view(graphiql=settings.GRAPHIQL, schema=schema))),
    # REST API base url
    path("api/", include("bigO.rest.api_router")),
    # REST API JWT
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    # REST API schema
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    # REST API docs
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="api-schema"),
        name="api-docs",
    ),
    bigO.proxy_manager.urls.sublink_view_path,
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


if settings.PLUGGABLE_FUNCS.DEBUG_TOOLBAR:
    import debug_toolbar

    urlpatterns.append(
        path("__debug__/", include(debug_toolbar.urls)),
    )
