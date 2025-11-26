from opentelemetry import metrics

meter = metrics.get_meter("telegram_bot")

update_total_counter = meter.create_counter(
    name="update.total",
    unit="update",
    description="Number of updates received",
)
