"""Authorized read-only customer ledger adapter. No imports, shipping or writes."""
from datetime import date, datetime, timedelta, timezone
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select

from app import db as database
from app.models.customer_order_ledger import OrderLedgerLine as Line
from app.services import customer_order_ledger as ledger, customer_order_queries as reader
from app.services.business_authz import has_permission_for_departments
from .errors import AssistantError
from .evidence import now_iso, stable_id
from .tool_result import validate_result

NAME = "list_customer_orders"
FACTORIES = {"huaxing", "huadeng", "huakang-a", "huakang-b", "huakang-c", "huakang-d"}
FACTORY_LABELS = dict(zip(("huaxing", "huadeng", "huakang-a", "huakang-b", "huakang-c", "huakang-d"),
                          ("华兴", "华登", "华康A", "华康B", "华康C", "华康D")))
DATA_FIELDS = ("po_no", "contract_no", "product_name_zh", "product_name_en", "requested_ship_date", "packaging",
               "units_per_carton", "carton_count", "standard", "country", "note", "recheck_notice")
ROW_FIELDS = {"resource_ref", "id", "factory_id", "customer_code", "customer_name", "reference_no", "product_no",
              "quantity", "shipped_quantity", "remaining_quantity", "status", "version", "revision", "dispatch_status",
              "updated_at", "order_fields", "requested_ship_date_known", "overdue", "detail", "truncated_fields"}
DEFINITIONS = {
    "orders.business_date.v1": "查询快照对应的上海业务日期；逾期判断以此日期为准，禁止从UTC日期或历史回答推断。",
    "orders.count.v1": "当前核准厂区及筛选范围中的订单台账行数；不等于PO单数或产品款数。",
    "orders.unfinished.v1": "有效订单且数量未知或订单数量大于已走货数量；数量未知保留待核对。",
    "orders.remaining.v1": "同一范围有效订单数量减已走货数量，取消订单贡献0；任一有效数量未知则完整总量未知。单位沿用原订单，未换算件/套/箱。",
    "orders.shipped.v1": "同一范围台账已走货数量，包含已有历史期初和冲回后的余额；不是生产数量。单位沿用原订单。",
    "orders.overdue.v1": "有效、已知未发完数量大于0，客户要求交期是有效日历日期且早于查询时上海业务日期；未知数量/日期使完整逾期数未知。",
    "orders.unknown_quantity.v1": "筛选范围内订单数量为null的行数，不把未知改成0。",
    "orders.unknown_due.v1": "未发完记录中数量或客户要求交期未知，无法判断是否逾期的行数。",
    "orders.cancelled.v1": "同一范围内status=cancelled的订单台账行数。",
}


def business_now():
    """Expose the explicit +08:00 offset instead of inviting UTC relabeling."""
    return datetime.fromisoformat(now_iso()).astimezone(timezone(timedelta(hours=8))).isoformat()


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    factory_id: str = Field(min_length=1, max_length=32)
    resource_id: str | None = Field(default=None, min_length=1, max_length=64)
    customer_code: str = Field(default="", max_length=64)
    view: Literal["all", "unshipped", "shipped", "cancelled"] = "all"
    q: str = Field(default="", max_length=255)
    date_from: str | None = Field(default=None, max_length=10)
    date_to: str | None = Field(default=None, max_length=10)
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def valid(self):
        for value in (self.date_from, self.date_to):
            if value is not None and date.fromisoformat(value).isoformat() != value:
                raise ValueError("invalid date")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date range reversed")
        if self.resource_id and (self.cursor or self.q or self.customer_code or self.view != "all" or self.date_from or self.date_to):
            raise ValueError("detail selection cannot silently combine unrelated filters")
        return self


def authorize(user, factory):
    if factory not in FACTORIES:
        raise AssistantError("factory_unavailable", "请选择客户订单支持的明确厂区。", 422)
    if not has_permission_for_departments(user, "customer_order:read", factory, ("sales-business",)):
        raise AssistantError("business_forbidden", "无当前范围的订单读取权限。", 403)


def exists(db, factory, ident):
    return bool(db.scalar(select(Line.id).where(Line.id == ident, Line.factory_id == factory)))


def operational(data):
    # Re-tighten the native read projection. Never forward arbitrary extensions,
    # prices, parser lineage, source binaries, or nested client-controlled JSON.
    return {key: str(data[key])[:1000] for key in DATA_FIELDS
            if isinstance(data.get(key), (str, int, float)) and not isinstance(data.get(key), bool)}


def row_out(db, row, today, detail=False):
    value = ledger.line_out(db, row)
    due = reader.requested_date(row.data)
    remaining = None if row.quantity is None else row.quantity - row.shipped_quantity
    item = {key: value[key] for key in ROW_FIELDS - {"resource_ref", "order_fields", "requested_ship_date_known", "overdue", "detail", "truncated_fields"}}
    item.update(resource_ref=f"customer-orders:order:{row.id}", order_fields=operational(row.data),
                requested_ship_date_known=due is not None,
                truncated_fields=[key for key in DATA_FIELDS if isinstance(row.data.get(key), str) and len(row.data[key]) > 1000],
                overdue=False if row.status == "cancelled" or remaining == 0 else None if due is None or remaining is None else due < today)
    # Native blank quantity represents unknown; explicit null is safer to models.
    for key in ("quantity", "remaining_quantity"):
        if item[key] == "": item[key] = None
    if detail:
        original = ledger.detail(db, row, history_limit=20)
        item["detail"] = dict(
            versions=[dict(version=v["version"], created_at=v["created_at"], order_fields=operational(v["data"])) for v in original["versions"][:20]],
            shipments=[{k: s[k] for k in ("quantity", "ship_date", "document_no", "reversed", "created_at")} for s in original["shipments"][:20]],
            version_count=original["history_counts"]["versions"], shipment_count=original["history_counts"]["shipments"],
            history_truncated=original["history_counts"]["versions"] > 20 or original["history_counts"]["shipments"] > 20)
    return item


def query(user, arguments, run_id, *, tool_call_id=None, step_id=None):
    try:
        args = Arguments.model_validate(arguments)
    except (ValidationError, ValueError):
        raise AssistantError("tool_invalid", "订单查询参数无效；请核对厂区、筛选、日期或分页。", 422) from None
    authorize(user, args.factory_id)
    requested_at = business_now()
    with database.SessionLocal() as db:
        # Keep count, rows, metrics and evidence on one read snapshot.
        if db.get_bind().dialect.name == "sqlite":
            db.connection().exec_driver_sql("BEGIN")
        elif db.get_bind().dialect.name == "postgresql":
            db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        from .business import fingerprint
        auth = fingerprint(db, user)
        filters = {k: v for k, v in args.model_dump().items() if k in {"customer_code", "view", "q", "date_from", "date_to"} and v not in (None, "")}
        filters["view"] = args.view
        scope_key = stable_id(auth, args.factory_id, json.dumps(filters, sort_keys=True), args.resource_id)
        offset = 0
        if args.cursor:
            try:
                key, number = args.cursor.split(":")
                if key != scope_key or not number.isascii() or not number.isdigit() or int(number) > 10000000:
                    raise ValueError
                offset = int(number)
            except ValueError:
                raise AssistantError("cursor_invalid", "分页范围已变化，请从第一页重新查询。", 422) from None
        stmt = reader.statement(args.factory_id, customer_code=args.customer_code, view=args.view, q=args.q,
            resource_id=args.resource_id, date_from=date.fromisoformat(args.date_from) if args.date_from else None,
            date_to=date.fromisoformat(args.date_to) if args.date_to else None)
        as_of = business_now()
        totals = reader.progress(db, stmt, today=datetime.fromisoformat(as_of).date())
        total, rows = reader.read_slice(db, stmt, offset=offset, limit=args.limit)
        if args.resource_id and not rows:
            raise AssistantError("source_unavailable", "订单不存在或不在当前可见范围。", 404)
        if offset and offset >= total:
            raise AssistantError("cursor_invalid", "订单列表已变化，请从第一页重新查询。", 422)
        today = date.fromisoformat(totals["as_of_date"])
        items = [row_out(db, row, today, bool(args.resource_id)) for row in rows]
        resources = [dict(module_id="customer-orders", resource_type="order", resource_id=r.id) for r in rows]
        refs = [item["resource_ref"] for item in items]
        unknowns = []
        if any(item["truncated_fields"] for item in items):
            unknowns.append(dict(field="order_fields", reason="部分长文本仅返回前1000字；请打开原订单查看全文。"))
        if any(item.get("detail", {}).get("history_truncated") for item in items):
            unknowns.append(dict(field="detail.history", reason="仅返回最近20条版本和走货记录；总数保留，完整历史请打开原订单核对。"))
        if totals["remaining_unknown_count"]:
            unknowns.append(dict(field="remaining_quantity", reason="有效订单中存在未知数量，完整未发数量无法确定。"))
        if totals["overdue_unknown_count"]:
            unknowns.append(dict(field="overdue_count", reason="未发完订单中存在未知数量或无效/缺失交期，完整逾期数无法确定。"))
        def metric(value, unit, definition):
            return dict(value=value, unit=unit, definition_id=definition, status="unknown" if value is None else "known")
        metrics = {
            "order_count": metric(total, "订单行", "orders.count.v1"),
            "unfinished_count": metric(totals["unfinished_count"], "订单行", "orders.unfinished.v1"),
            "remaining_quantity": metric(None if totals["remaining_unknown_count"] else totals["remaining_quantity"], "原订单数量单位", "orders.remaining.v1"),
            "shipped_quantity": metric(totals["shipped_quantity"], "原订单数量单位", "orders.shipped.v1"),
            "overdue_count": metric(None if totals["overdue_unknown_count"] else totals["overdue_count"], "订单行", "orders.overdue.v1"),
            "unknown_quantity_count": metric(totals["unknown_quantity_count"], "订单行", "orders.unknown_quantity.v1"),
            "overdue_unknown_count": metric(totals["overdue_unknown_count"], "订单行", "orders.unknown_due.v1"),
            "cancelled_count": metric(totals["cancelled_count"], "订单行", "orders.cancelled.v1"),
        }
        retrieved_at = business_now()
        selected = bool(args.resource_id)
        scope_label = FACTORY_LABELS[args.factory_id] + (" / 选中订单" if selected else " / 订单台账" + (" / 已筛选" if any(v not in ("all", "", None) for v in filters.values()) else ""))
        source_id = stable_id(run_id, NAME, scope_key, offset, as_of)
        source = dict(kind="business", source_id=source_id, run_id=run_id, title="客户订单台账", tool_name=NAME,
            resources=resources, scope=dict(factory_id=args.factory_id, scope_label=scope_label, authorization="current_user", filters=filters),
            as_of=as_of, observed_at=None, retrieved_at=retrieved_at, data_mode="snapshot", unknown_fields=[u["reason"] for u in unknowns],
            authorization_fingerprint=auth)
        actions = [dict(type="open_record", label="打开原订单："+r.reference_no[:60], route_name="customer-order-center", params={},
            query=dict(factory=args.factory_id, order=r.id), resource=resource) for r, resource in zip(rows, resources)]
        truncated = offset + len(rows) < total
        result = dict(record_type="tool_result", contract_version=3, tool_name=NAME, tool_version="orders-v3.1",
            tool_call_id=tool_call_id or stable_id(run_id, scope_key, offset), run_id=run_id, step_id=step_id or NAME,
            status="empty" if total == 0 else "partial" if truncated or unknowns else "ok",
            scope=dict(factory_ids=[args.factory_id], module_id="customer-orders", filters=filters,
                resource_refs=refs if selected else [], coverage="selected_resources" if selected else "filtered_scope" if scope_label.endswith("已筛选") else "authorized_scope", label=scope_label),
            requested_at=requested_at, as_of=as_of, observed_at=None, retrieved_at=retrieved_at, timezone="Asia/Shanghai", business_date=totals["as_of_date"],
            data_mode="snapshot", freshness=dict(state="fresh", max_age_seconds=30, cache_hit=False, cache_created_at=None, policy_id="orders-current-v1"),
            metrics=metrics, rows=items, total_count=total, returned_count=len(items), truncated=truncated,
            next_cursor=f"{scope_key}:{offset+len(rows)}" if truncated else None, definitions=DEFINITIONS,
            unknown_fields=unknowns, source_refs=[source_id],
            allowed_actions=[dict(action_id=stable_id(source_id, ref), kind="navigate", label=action["label"], resource_ref=ref) for ref, action in zip(refs, actions)],
            diagnostic_code=None)
        return validate_result(result, registered_sources=[source_id], registered_resources=refs, row_fields=ROW_FIELDS), source, actions
