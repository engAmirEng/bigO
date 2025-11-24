import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, SERVICE_NAME, SERVICE_NAMESPACE, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class TeleportConfig(AppConfig):
    name = "bigO.core"
    verbose_name = _("Core")

    def ready(self):
        # configure OTEL exporter
        trace_processor = None
        metric_reader = None
        if settings.OTEL_DEBUG:
            trace_processor = BatchSpanProcessor(ConsoleSpanExporter())
            metric_reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
        elif settings.OTEL_ENDPOINT:
            headers = {"Authorization": settings.OTEL_AUTH}
            trace_processor = BatchSpanProcessor(
                OTLPSpanExporter(endpoint=f"{settings.OTEL_ENDPOINT}/v1/traces", headers=headers)
            )
            metric_reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{settings.OTEL_ENDPOINT}/v1/metrics", headers=headers)
            )

        resource = Resource.create(
            attributes={
                SERVICE_NAME: "bigO",
                SERVICE_NAMESPACE: "bigO",
                DEPLOYMENT_ENVIRONMENT: "develop",
            }
        )
        if trace_processor:
            tracerProvider = TracerProvider(resource=resource)
            tracerProvider.add_span_processor(trace_processor)
            trace.set_tracer_provider(tracerProvider)
        if metric_reader:
            meterProvider = MeterProvider(resource=resource, metric_readers=[metric_reader])
            metrics.set_meter_provider(meterProvider)
