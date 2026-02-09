from opentelemetry import metrics

meter = metrics.get_meter("proxy_manager")

sublink_request_total_counter = meter.create_counter(
    name="sublink.request.total",
    unit="1",
    description="Number of sublink requests",
)
