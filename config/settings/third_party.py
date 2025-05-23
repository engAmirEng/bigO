from datetime import timedelta

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from ._setup import PLUGGABLE_FUNCS, clean_ellipsis, env
from .django import DEBUG

# Celery
# ------------------------------------------------------------------------------
CELERY_TIMEZONE = "UTC"
CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = "django-db"
CELERY_RESULT_EXTENDED = True
CELERY_RESULT_BACKEND_ALWAYS_RETRY = True
CELERY_RESULT_BACKEND_MAX_RETRIES = 10
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_TIME_LIMIT = 5 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 60
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#worker-send-task-events
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_TASK_SEND_SENT_EVENT = True
CELERY_TASK_EAGER_PROPAGATES = True

# django-axes
# ------------------------------------------------------------------------------
AXES_CLIENT_IP_CALLABLE = "bigO.utils.ip.get_client_ip"

# django-debug-toolbar
# ------------------------------------------------------------------------------
DEBUG_TOOLBAR_CONFIG = {
    "DISABLE_PANELS": ["debug_toolbar.panels.redirects.RedirectsPanel"],
    "SHOW_TEMPLATE_CONTEXT": True,
}

# graphene-django
# ------------------------------------------------------------------------------
GRAPHENE = {
    "MIDDLEWARE": clean_ellipsis(
        [
            "graphene_django.debug.DjangoDebugMiddleware" if PLUGGABLE_FUNCS.DEBUG_TOOLBAR else ...,
            "graphql_jwt.middleware.JSONWebTokenMiddleware",
        ]
    )
}

CORS_URLS_REGEX = r"^/api/.*$|^/graphql/$"

# django-graphql-jwt
# ------------------------------------------------------------------------------
GRAPHQL_JWT = {
    "JWT_VERIFY_EXPIRATION": True,
    "JWT_EXPIRATION_DELTA": timedelta(minutes=5),
    "JWT_REFRESH_EXPIRATION_DELTA": timedelta(days=7),
    "JWT_LONG_RUNNING_REFRESH_TOKEN": True,
}

# django-rest-framework
# -------------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": clean_ellipsis(
        [
            "rest_framework.renderers.JSONRenderer",
            "rest_framework.renderers.BrowsableAPIRenderer" if DEBUG else ...,
        ]
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# drf-spectacular
# -------------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "bigO API",
    "DESCRIPTION": "Documentation of API endpoints of bigO",
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
}

# Sentry
# -------------------------------------------------------------------------------
if sentry_dsn := env.url("SENTRY_DSN", default=None):
    sentry_sdk.init(
        dsn=sentry_dsn.geturl(),
        integrations=[DjangoIntegration()],
        auto_session_tracking=False,
        traces_sample_rate=0.05,
    )

# django-vite
DJANGO_VITE = {"BabyUI": {"dev_mode": DEBUG, "dev_server_port": 5225, "static_url_prefix": "BabyUI"}}  # todo  # todo
