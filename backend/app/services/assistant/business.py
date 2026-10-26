"""Bounded, read-only adapters. Authorization is the existing module policy."""
from sqlalchemy import select
from .errors import AssistantError
from .help_registry import supplier_only
from .registry import CALLABLE
from . import orders, work_items, injection, printers, cartons, quotes, uv, spray

NAMES = {c.tool_name for c in CALLABLE}
ROUTES = {c.tool_name: (c.module_id, c.route_name) for c in CALLABLE}
TOOLS = [{"type": "function", "function": {"name": name, "description": description,
    "parameters": spray.Arguments.model_json_schema() if name == spray.NAME else uv.Arguments.model_json_schema() if name == uv.NAME else quotes.Arguments.model_json_schema() if name == quotes.NAME else orders.Arguments.model_json_schema() if name == orders.NAME else work_items.Arguments.model_json_schema() if name == work_items.NAME else injection.Arguments.model_json_schema() if name == injection.NAME else printers.Arguments.model_json_schema() if name == printers.NAME else cartons.Arguments.model_json_schema() if name == cartons.NAME else
        {"type": "object", "properties": {"factory_id": {"type": "string"}, "resource_id": {"type": "string", "maxLength": 160}},
                   "required": ["factory_id"], "additionalProperties": False}}}
    for name, description in ((c.tool_name, c.description) for c in CALLABLE)]


def fingerprint(db, user):
    from .auth_snapshot import fingerprint as stable_fingerprint
    return stable_fingerprint(db, user)


def authorize(db, user, name, factory):
    if user is None or supplier_only(user):
        raise AssistantError("business_forbidden", "当前身份不可使用内部业务查询。", 403)
    if name == "get_my_work":
        from app.services.auth import ALLOWED_FACTORY_IDS
        if factory not in ("authorized", *ALLOWED_FACTORY_IDS):
            raise AssistantError("factory_unavailable", "请选择有效厂区或本人授权范围。", 422)
    elif name == "get_injection_overview":
        from app.services.business_authz import has_permission_for_departments
        if factory not in ("huaxing", "huadeng", "huakang-a", "huakang-b"):
            raise AssistantError("factory_unavailable", "注塑排期仅支持华兴、华灯、华康A和华康B。", 422)
        if not has_permission_for_departments(user, "injection_scheduling:read", factory, ("production", "molding", "management")):
            raise AssistantError("business_forbidden", "无当前范围的注塑读取权限。", 403)
    elif name == "get_printer_status":
        from app.services.auth import has_permission_in_scope
        from app.services.three_d_printing import require_three_d_factory, THREE_D_DEPARTMENTS
        factory = require_three_d_factory(factory)
        if not any(has_permission_in_scope(user, "three_d_printing:read", factory, d) for d in THREE_D_DEPARTMENTS):
            raise AssistantError("business_forbidden", "无当前范围的3D读取权限。", 403)
    elif name == orders.NAME:
        orders.authorize(user, factory)
    elif name == cartons.NAME:
        cartons.authorize(db, user, factory)
    elif name == quotes.NAME:
        quotes.authorize(user, factory)
    elif name == uv.NAME:
        uv.authorize(db, user, factory)
    elif name == spray.NAME:
        spray.authorize(db, user, factory)
    else:
        raise AssistantError("tool_invalid", "此业务查询未注册。")


def query(user, name, arguments, run_id, *, tool_call_id=None, step_id=None):
    if name == spray.NAME:
        return spray.query(user, arguments, run_id, tool_call_id=tool_call_id, step_id=step_id)
    if name == uv.NAME:
        return uv.query(user, arguments, run_id, tool_call_id=tool_call_id, step_id=step_id)
    if name == quotes.NAME:
        return quotes.query(user, arguments, run_id, tool_call_id=tool_call_id, step_id=step_id)
    if name == cartons.NAME:
        return cartons.query(user, arguments, run_id, tool_call_id=tool_call_id, step_id=step_id)
    if name == printers.NAME:
        return printers.query(user, arguments, run_id, tool_call_id=tool_call_id, step_id=step_id)
    if name == injection.NAME:
        return injection.query(user, arguments, run_id, tool_call_id=tool_call_id, step_id=step_id)
    if name == work_items.NAME:
        return work_items.query(user, arguments, run_id, tool_call_id=tool_call_id, step_id=step_id)
    if name == orders.NAME:
        if user is None or supplier_only(user):
            raise AssistantError("business_forbidden", "当前身份不可使用内部业务查询。", 403)
        return orders.query(user, arguments, run_id, tool_call_id=tool_call_id, step_id=step_id)
    raise AssistantError("tool_invalid", "此业务查询未注册。")


def visible(db, user, source):
    name = source.get("tool_name")
    factory = source.get("scope", {}).get("factory_id") or "authorized"
    authorize(db, user, name, factory)
    from .auth_snapshot import matches
    if not matches(db, user, source.get("authorization_fingerprint")):
        return False
    if name == cartons.NAME:
        return cartons.visible(db, user, source)
    if name == quotes.NAME:
        return quotes.visible(db, user, source)
    if name == uv.NAME:
        return uv.visible(db, user, source)
    if name == spray.NAME:
        return spray.visible(db, user, source)
    for resource in source.get("resources", []):
        ident = resource["resource_id"]
        if name == "get_my_work":
            from app.services.work_center.service import detail
            detail(db, user, ident)
        elif name == "get_injection_overview":
            from app.models.injection_scheduling import Demand
            if not db.scalar(select(Demand.id).where(Demand.id == ident, Demand.factory_id == factory)):
                return False
        elif name == orders.NAME:
            if resource.get("module_id") != "customer-orders" or resource.get("resource_type") != "order" or not orders.exists(db, factory, ident):
                return False
        else:
            from app.models.three_d_printing import ThreeDPrintingPrinter
            if not db.scalar(select(ThreeDPrintingPrinter.id).where(ThreeDPrintingPrinter.id == ident, ThreeDPrintingPrinter.factory_id == factory)):
                return False
    return True
