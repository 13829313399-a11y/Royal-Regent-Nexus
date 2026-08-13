from __future__ import annotations

from dataclasses import dataclass

from app.schemas.ai.query_plan import AIQueryOperation, AIQueryOperator


@dataclass(frozen=True, slots=True)
class AIEntityField:
    id: str
    operators: frozenset[AIQueryOperator]
    tool_argument_by_operator: tuple[tuple[AIQueryOperator, str], ...]
    value_kind: str = "TEXT"
    sortable: bool = False
    allowed_sort_directions: tuple[str, ...] = ()

    def tool_argument(self, operator: AIQueryOperator) -> str | None:
        return dict(self.tool_argument_by_operator).get(operator)


@dataclass(frozen=True, slots=True)
class AIEntityDefinition:
    id: str
    domain: str
    module_id: str
    tool_name: str
    operations: frozenset[AIQueryOperation]
    fields: tuple[AIEntityField, ...]
    metric_ids: frozenset[str]
    default_sort: tuple[tuple[str, str], ...] = ()
    authoritative_ledger: bool = True

    def field(self, field_id: str) -> AIEntityField | None:
        return next((item for item in self.fields if item.id == field_id), None)


_ENTITIES = (
    AIEntityDefinition(
        id="scheduling_backlog_order",
        domain="injection_scheduling",
        module_id="injection-scheduling",
        tool_name="semantic.injection_scheduling.query_backlog",
        operations=frozenset({AIQueryOperation.LIST}),
        fields=(
            AIEntityField(
                id="due_date",
                operators=frozenset(
                    {AIQueryOperator.EQ, AIQueryOperator.GTE, AIQueryOperator.LTE}
                ),
                tool_argument_by_operator=(
                    (AIQueryOperator.EQ, "due_date_eq"),
                    (AIQueryOperator.GTE, "due_date_gte"),
                    (AIQueryOperator.LTE, "due_date_lte"),
                ),
                value_kind="DATE",
                sortable=True,
                allowed_sort_directions=("ASC", "DESC"),
            ),
            AIEntityField(
                id="order_no",
                operators=frozenset({AIQueryOperator.EQ}),
                tool_argument_by_operator=((AIQueryOperator.EQ, "order_no"),),
                value_kind="BUSINESS_ID",
            ),
            AIEntityField(
                id="item_no",
                operators=frozenset({AIQueryOperator.EQ}),
                tool_argument_by_operator=((AIQueryOperator.EQ, "item_no"),),
                value_kind="BUSINESS_ID",
            ),
            AIEntityField(
                id="mold_no",
                operators=frozenset({AIQueryOperator.EQ}),
                tool_argument_by_operator=((AIQueryOperator.EQ, "mold_no"),),
                value_kind="BUSINESS_ID",
            ),
            AIEntityField(
                id="priority",
                operators=frozenset({AIQueryOperator.EQ}),
                tool_argument_by_operator=((AIQueryOperator.EQ, "priority_code"),),
                value_kind="PRIORITY",
            ),
        ),
        metric_ids=frozenset({"scheduling.backlog_count"}),
        default_sort=(("due_date", "ASC"),),
    ),
    AIEntityDefinition(
        id="internal_quote_summary",
        domain="internal_quote",
        module_id="internal-quote",
        tool_name="internal_quote.list_summaries",
        operations=frozenset({AIQueryOperation.LIST}),
        fields=(
            AIEntityField(
                id="status",
                operators=frozenset({AIQueryOperator.EQ}),
                tool_argument_by_operator=((AIQueryOperator.EQ, "status"),),
                value_kind="QUOTE_STATUS",
            ),
            AIEntityField(
                id="keyword",
                operators=frozenset({AIQueryOperator.CONTAINS}),
                tool_argument_by_operator=((AIQueryOperator.CONTAINS, "keyword"),),
                value_kind="LITERAL_TEXT",
            ),
            AIEntityField(
                id="updated_at",
                operators=frozenset(),
                tool_argument_by_operator=(),
                value_kind="DATETIME",
                sortable=True,
                allowed_sort_directions=("DESC",),
            ),
        ),
        metric_ids=frozenset({"internal_quote.summary_count"}),
        default_sort=(("updated_at", "DESC"),),
    ),
    AIEntityDefinition(
        id="customer_order_capability",
        domain="customer_order",
        module_id="customer-order",
        tool_name="customer_order.get_capabilities",
        operations=frozenset({AIQueryOperation.LIST}),
        fields=(),
        metric_ids=frozenset(),
        authoritative_ledger=False,
    ),
    AIEntityDefinition(
        id="customer_order_export_audit",
        domain="customer_order",
        module_id="customer-order",
        tool_name="customer_order.list_export_audits",
        operations=frozenset({AIQueryOperation.LIST}),
        fields=(
            AIEntityField(
                id="customer_code",
                operators=frozenset({AIQueryOperator.EQ}),
                tool_argument_by_operator=((AIQueryOperator.EQ, "customer_code"),),
                value_kind="BUSINESS_ID",
            ),
            AIEntityField(
                id="created_at",
                operators=frozenset(),
                tool_argument_by_operator=(),
                value_kind="DATETIME",
                sortable=True,
                allowed_sort_directions=("DESC",),
            ),
        ),
        metric_ids=frozenset(),
        default_sort=(("created_at", "DESC"),),
        authoritative_ledger=False,
    ),
)

ENTITY_CATALOG_VERSION = "semantic-entity-catalog-v1"
ENTITY_CATALOG = {item.id: item for item in _ENTITIES}


def get_entity(entity_id: str) -> AIEntityDefinition | None:
    return ENTITY_CATALOG.get(entity_id)
