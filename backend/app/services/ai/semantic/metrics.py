from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AIMetricDefinition:
    id: str
    entity_id: str
    # A reviewed server operation, never a formula or expression supplied to a model.
    service_operation: str
    result_field: str


METRIC_CATALOG_VERSION = "semantic-metric-catalog-v1"
_METRICS = (
    AIMetricDefinition(
        id="scheduling.backlog_count",
        entity_id="scheduling_backlog_order",
        service_operation="injection_scheduling.query_backlog",
        result_field="total",
    ),
    AIMetricDefinition(
        id="internal_quote.summary_count",
        entity_id="internal_quote_summary",
        service_operation="internal_quote.list_summaries",
        result_field="total",
    ),
)
METRIC_CATALOG = {item.id: item for item in _METRICS}


def get_metric(metric_id: str) -> AIMetricDefinition | None:
    return METRIC_CATALOG.get(metric_id)
