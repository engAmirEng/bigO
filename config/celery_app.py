import os

from celery import Celery
from celery.signals import worker_init, worker_process_init
from opentelemetry.instrumentation.celery import CeleryInstrumentor

from . import otel_config

# set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


@worker_init.connect
def worker_init_handler(sender, **kwargs):
    pool_cls = str(sender.pool_cls) if hasattr(sender, "pool_cls") else None

    if "threads" in pool_cls:  # only if --pool=threads
        # configure open-telemetry
        opentelemetry_configured = otel_config.configure_opentelemetry()
        if opentelemetry_configured:
            CeleryInstrumentor().instrument()


@worker_process_init.connect(weak=False)
def worker_process_init_handler(**kwargs):
    # configure open-telemetry
    opentelemetry_configured = otel_config.configure_opentelemetry()
    if opentelemetry_configured:
        CeleryInstrumentor().instrument()


app = Celery("bigO")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()
