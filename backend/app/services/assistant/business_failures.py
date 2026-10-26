"""Safe unavailable results for independent business queries, never evidence."""
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from .errors import AssistantError
from .evidence import now_iso
from .registry import CALLABLE
from .tool_result import validate_result


REASONS = {
    "business_forbidden": "当前身份无此范围的读取权限",
    "source_unavailable": "原记录不存在或不在当前可见范围",
    "factory_unavailable": "当前厂区不支持此项查询",
    "tool_invalid": "查询参数未通过校验",
    "cursor_invalid": "分页范围或数据版本已变化，需要重新查询",
    "module_disabled": "模块尚未启用",
    "schema_not_ready": "模块尚未完成初始化",
    "business_query_failed": "该领域暂时无法读取",
}
ALIASES = {"permission_denied": "business_forbidden", "factory_required": "factory_unavailable"}


def unavailable(exc, name, arguments, run_id, *, tool_call_id, step_id, requested_at):
    """Only domain failures are recoverable. Identity/control errors remain fatal.

    Raw exception details and supplied resource IDs/filters must not enter model
    input, UI, history or exports through a failed result.
    """
    connector = next((c for c in CALLABLE if c.tool_name == name), None)
    if connector is None:
        raise exc
    if isinstance(exc, AssistantError):
        code = ALIASES.get(exc.detail["code"], exc.detail["code"])
        if code not in REASONS:
            raise exc
    elif isinstance(exc, HTTPException):
        code = {400: "tool_invalid", 403: "business_forbidden", 404: "source_unavailable",
                422: "tool_invalid", 503: "business_query_failed"}.get(exc.status_code)
        if code is None:
            raise exc
    elif isinstance(exc, SQLAlchemyError):
        code = "business_query_failed"
    else:
        raise exc
    from app.services.auth import ALLOWED_FACTORY_IDS
    factory = arguments.get("factory_id") if isinstance(arguments, dict) else None
    factories = [factory] if isinstance(factory, str) and factory in ALLOWED_FACTORY_IDS else []
    result = dict(record_type="tool_result", contract_version=3, tool_name=name, tool_version="3.0",
        tool_call_id=tool_call_id, run_id=run_id, step_id=step_id,
        status="forbidden" if code == "business_forbidden" else "failed",
        scope=dict(factory_ids=factories, module_id=connector.module_id, filters={}, resource_refs=[],
                   coverage="selected_resources" if isinstance(arguments, dict) and arguments.get("resource_id") else "filtered_scope",
                   label=connector.label + " · 未取得数据"),
        requested_at=requested_at, as_of=None, observed_at=None, retrieved_at=now_iso(), timezone="UTC",
        business_date=None, data_mode="unavailable",
        freshness=dict(state="unknown", max_age_seconds=None, cache_hit=False, cache_created_at=None,
                       policy_id="business-unavailable-v3"),
        metrics={}, rows=[], total_count=None, returned_count=0, truncated=False, next_cursor=None,
        definitions={}, unknown_fields=[dict(field="query", reason=REASONS[code])],
        source_refs=[], allowed_actions=[], diagnostic_code=code)
    return validate_result(result, registered_sources=[], registered_resources=[], row_fields=[])


def notice(result):
    connector = next(c for c in CALLABLE if c.tool_name == result["tool_name"])
    return f"\n\n查询范围说明：{connector.label}未取得数据（{REASONS[result['diagnostic_code']]}）；该范围的数量与风险仍未知。\n\n"
