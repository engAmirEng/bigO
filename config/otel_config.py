import os
import socket

import opentelemetry.sdk.environment_variables
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, SERVICE_NAME, SERVICE_INSTANCE_ID, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

_ALREADY = False


def configure_opentelemetry():
    global _ALREADY
    if _ALREADY:  # avoids the “Overriding …” warnings
        return _ALREADY
    _ALREADY = True

    if os.environ.get(opentelemetry.sdk.environment_variables.OTEL_SDK_DISABLED, ""):
        _ALREADY = False
        return _ALREADY
    if os.environ.get("OTEL_DEBUG", ""):
        trace_exporter = ConsoleSpanExporter()
        metric_exporter = ConsoleMetricExporter()
    else:
        trace_exporter = OTLPSpanExporter()
        metric_exporter = OTLPMetricExporter()
    trace_processor = BatchSpanProcessor(trace_exporter)
    metric_reader = PeriodicExportingMetricReader(metric_exporter)

    resource = Resource.create(
        attributes={
            SERVICE_NAME: "bigO",
            DEPLOYMENT_ENVIRONMENT: os.environ.get("OTEL_DEPLOYMENT_ENVIRONMENT", "develop"),
            SERVICE_INSTANCE_ID: f"{socket.gethostname()}-{os.getpid()}",  # maybe uuid.uuid4()
        }
    )
    if trace_processor:
        tracerProvider = TracerProvider(resource=resource)
        tracerProvider.add_span_processor(trace_processor)
        trace.set_tracer_provider(tracerProvider)
    if metric_reader:
        meterProvider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meterProvider)

    DjangoInstrumentor().instrument()
