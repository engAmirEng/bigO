import atexit
import os
import queue
from logging.handlers import QueueListener

import environ

import django.core.exceptions
from bigO.utils.logging import BasicLokiHandler
from django.utils.translation import gettext_lazy as __

from ._setup import APPS_DIR, BASE_DIR, PLUGGABLE_FUNCS, clean_ellipsis, log_ignore_modules

# Set defaults
defaults = {}
env = environ.Env(**defaults)
# SECURITY
# ------------------------------------------------------------------------------
DEBUG = env.bool("DJANGO_DEBUG", False)
SECRET_KEY = env.str("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "0.0.0.0", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=["http://localhost", "http://0.0.0.0", "http://127.0.0.1"],
)

INTERNAL_IPS = ["127.0.0.1", "10.0.2.2"]
if env("USE_DOCKER") == "yes":
    import socket

    hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS += [".".join(ip.split(".")[:-1] + ["1"]) for ip in ips]
SECURE_PROXY_SSL_HEADER = env.tuple("DJANGO_SECURE_PROXY_SSL_HEADER", default=("HTTP_X_FORWARDED_PROTO", None))
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = env.bool("DJANGO_SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("DJANGO_CSRF_COOKIE_SECURE", default=False)
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = "DENY"

# GENERAL
# ------------------------------------------------------------------------------
ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

# I18N and L10N
# ------------------------------------------------------------------------------
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
LANGUAGES = [
    ("en", __("English")),
    ("fa", __("Persian")),
    ("ar", __("Arabic")),
]
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [str(BASE_DIR / "locale")]

# DATABASES
# ------------------------------------------------------------------------------
try:
    # TODO why try except?
    # when DATABASE_URL="" then env("DATABASE_URL", default=None) returns None!!

    # just for "docs" and to run project in a dummy mode
    DATABASES = {"default": env.db("DATABASE_URL"), "stats": env.db("STATS_DATABASE_URL")}
except django.core.exceptions.ImproperlyConfigured:
    main_db = {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": env.str("POSTGRES_HOST"),
        "NAME": env.str("POSTGRES_DB"),
        "PASSWORD": env.str("POSTGRES_PASSWORD"),
        "PORT": env.int("POSTGRES_PORT"),
        "USER": env.str("POSTGRES_USER"),
        "CONN_MAX_AGE": env.int("CONN_MAX_AGE", default=0),
    }
    DATABASES = {
        # this is here because packages are stupid otherwise we won't reference 'default' anywhere
        "default": main_db,
        "main": main_db,
        "stats": {},
    }
    DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=0)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


DATABASE_ROUTERS = ["config.db_routers.DBRouter"]

# CACHES
# ------------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # Mimicing memcache behavior.
            "IGNORE_EXCEPTIONS": True,
        },
    }
}

# APPS
# ------------------------------------------------------------------------------
LOCAL_APPS = [
    "bigO.core",
    "bigO.node_manager",
    "bigO.proxy_manager",
    "bigO.users",
    "bigO.utils",
    "bigO.BabyUI",
]
THIRD_PARTY_APPS = clean_ellipsis(
    [
        "admin_extra_buttons",
        "axes",
        "solo",
        "corsheaders",
        "debug_toolbar" if PLUGGABLE_FUNCS.DEBUG_TOOLBAR else ...,
        "django_celery_beat",
        "django_celery_results",
        "django_filters",
        "django_htmx",
        "django_json_widget",
        "django_jsonform",
        "django_vite",
        "drf_spectacular",
        "graphene_django",
        "graphql_jwt.refresh_token",
        "inertia",
        "netfields",
        "polymorphic",
        "rest_framework",
        "rest_framework_api_key",
        "rest_framework_simplejwt",
        "taggit",
        "whitenoise.runserver_nostatic",
        # make sure any runserver command is after whitenoise's
        "daphne" if PLUGGABLE_FUNCS.DAPHNE else ...,
        # django_cleanup should be placed last
        "django_cleanup.apps.CleanupConfig",
    ]
)

DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.humanize",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django.forms",
]
INSTALLED_APPS = LOCAL_APPS + THIRD_PARTY_APPS + DJANGO_APPS

# AUTHENTICATION
# ------------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    # AxesStandaloneBackend should be the first
    "axes.backends.AxesStandaloneBackend",
    "graphql_jwt.backends.JSONWebTokenBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AUTH_USER_MODEL = "users.User"
LOGIN_REDIRECT_URL = "users:redirect"
LOGIN_URL = "account_login"

# PASSWORDS
# ------------------------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = (
    [
        {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
        {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
        {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
        {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    ]
    if not PLUGGABLE_FUNCS.NO_PASS_VALIDATION
    else []
)

# MIDDLEWARE
# ------------------------------------------------------------------------------
MIDDLEWARE = clean_ellipsis(
    [
        "debug_toolbar.middleware.DebugToolbarMiddleware" if PLUGGABLE_FUNCS.DEBUG_TOOLBAR else ...,
        "django.middleware.security.SecurityMiddleware",
        "corsheaders.middleware.CorsMiddleware",
        "whitenoise.middleware.WhiteNoiseMiddleware" if PLUGGABLE_FUNCS.SERVE_STATICFILES else ...,
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.locale.LocaleMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
        "django_htmx.middleware.HtmxMiddleware",
        "inertia.middleware.InertiaMiddleware",
        # It only formats user lockout messages and renders Axes lockout responses
        # on failed user authentication attempts from login views.
        # If you do not want Axes to override the authentication response
        # you can skip installing the middleware and use your own views.
        "axes.middleware.AxesMiddleware",
    ]
)

# STATIC
# ------------------------------------------------------------------------------
STATIC_ROOT = str(BASE_DIR / "staticfiles")
STATICFILES_DIRS = [
    BASE_DIR / "bigO" / "BabyUI" / "dist",
    (
        "BabyUI",
        BASE_DIR / "bigO" / "BabyUI" / "assets" / "public",
    ),
]
STATIC_URL = "/static/"
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# MEDIA
# ------------------------------------------------------------------------------
MEDIA_ROOT = str(BASE_DIR / "media")
MEDIA_URL = "/media/"

# TEMPLATES
# ------------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [str(APPS_DIR / "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "string_if_invalid": "templateerror",
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# FIXTURES
# ------------------------------------------------------------------------------
FIXTURE_DIRS = (str(APPS_DIR / "fixtures"),)

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = env.str("DJANGO_ADMIN_URL", "admin/")
# https://docs.djangoproject.com/en/dev/ref/settings/#admins

# TESTING
# ------------------------------------------------------------------------------
# The name of the class to use to run the test suite
TEST_RUNNER = "django.test.runner.DiscoverRunner"

# LOGGING
# ------------------------------------------------------------------------------
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "ignore_autoreload": {"()": "django.utils.log.CallbackFilter", "callback": log_ignore_modules(["autoreload"])}
    },
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOGS_DIR, "info.log"),
            "backupCount": env.int("MAX_LOG_FILE_COUNT", default=1),
            "maxBytes": 50 * 1024 * 1024,
            "filters": ["ignore_autoreload"],
            "formatter": "verbose",
        },
    },
    "root": {"level": "INFO", "handlers": ["console", "file"]},
}
if env("INFLUX_URL", default=None):
    INFLUX_URL = env.url("INFLUX_URL").geturl()
    INFLUX_ORG = env.str("INFLUX_ORG")
    INFLUX_BUCKET = env.str("INFLUX_BUCKET")
    INFLUX_TOKEN = env.str("INFLUX_TOKEN")
if env("LOKI_PUSH_ENDPOINT", default=None):
    LOKI_PUSH_ENDPOINT = env.url("LOKI_PUSH_ENDPOINT").geturl()
    LOKI_USERNAME = env.str("LOKI_USERNAME")
    LOKI_PASSWORD = env.str("LOKI_PASSWORD")
if env.bool("LOKI_LOGGING", default=False):
    # Define the log queue
    loki_log_queue = queue.Queue(-1)  # Use an unlimited queue size

    # Set up the Loki handler
    loki_handler = BasicLokiHandler(
        url=LOKI_PUSH_ENDPOINT,
        labels=env.json("LOKI_BASE_LABELS"),
        username=LOKI_USERNAME,
        password=LOKI_PASSWORD,
    )

    # Set up the QueueListener
    listener = QueueListener(loki_log_queue, loki_handler)
    listener.start()  # Start the listener in a background thread

    # Register the listener to stop on shutdown
    atexit.register(listener.stop)

    LOGGING["handlers"]["loki_handler"] = {
        "level": "WARNING",
        "class": "logging.handlers.QueueHandler",
        "queue": loki_log_queue,
    }
    LOGGING["root"]["handlers"].append("loki_handler")
