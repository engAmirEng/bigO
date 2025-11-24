import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, SERVICE_NAME, SERVICE_NAMESPACE, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

_ALREADY = False


def configure_opentelemetry():
    global _ALREADY
    if _ALREADY:  # avoids the “Overriding …” warnings
        return
    _ALREADY = True

    trace_processor = None
    metric_reader = None
    if os.environ.get("OTEL_DEBUG", False):
        trace_processor = BatchSpanProcessor(ConsoleSpanExporter())
        metric_reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
    elif os.environ.get("OTEL_ENDPOINT", None):
        headers = {"Authorization": os.environ["OTEL_AUTH"]}
        trace_processor = BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{os.environ['OTEL_ENDPOINT']}/v1/traces", headers=headers)
        )
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=f"{os.environ['OTEL_ENDPOINT']}/v1/metrics", headers=headers)
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

    DjangoInstrumentor().instrument()
