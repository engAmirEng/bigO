"""
ASGI config for bigO project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/dev/howto/deployment/asgi/

"""
import os
import sys
from pathlib import Path

from channels.routing import ProtocolTypeRouter
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

from django.core.asgi import get_asgi_application

from . import otel_config

# This allows easy placement of apps within the interior
# my_awesome_project directory.
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent
sys.path.append(str(BASE_DIR / "bigO"))
# If DJANGO_SETTINGS_MODULE is unset, default to the local settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# configure open-telemetry
opentelemetry_configured = otel_config.configure_opentelemetry()

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()
if opentelemetry_configured:
    django_asgi_app = OpenTelemetryMiddleware(django_asgi_app)


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
    }
)
if opentelemetry_configured:
    application = OpenTelemetryMiddleware(application)
