"""Bounded, read-only adapters. Authorization is the existing module policy."""
from fastapi import HTTPException
from sqlalchemy import select, func
from app import db as database
from .errors import AssistantError
from .evidence import now_iso, stable_id
from .help_registry import supplier_only

NAMES = {"get_my_work", "get_injection_overview", "get_printer_status"}
ROUTES = {"get_my_work": ("work-center", "notification-center"),
          "get_injection_overview": ("injection-scheduling", "injection-scheduling"),
          "get_printer_status": ("three-d-printing", "three-d-printing-management")}
TOOLS = [{"type": "function", "function": {"name": name, "description": description,
    "parameters": {"type": "object", "properties": {"factory_id": {"type": "string"}, "resource_id": {"type": "string", "maxLength": 160}},
                   "required": ["factory_id"], "additionalProperties": False}}}
    for name, description in (("get_my_work", "读取本人可见事项；统计区分全授权与选中厂区，未覆盖领域不推断为零"),
        ("get_injection_overview", "读取四厂注塑排期；held非缺料，剩余用料非库存缺口，排期风险非实际延期"),
        ("get_printer_status", "读取华康A机台快照与新鲜度，不控制设备，过期遥测不能断言物理停机"))]


def fingerprint(db, user):
    from app.services.work_center.service import context
    return context(db, user)[1]


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
    else:
        raise AssistantError("tool_invalid", "此业务查询未注册。")


def query(user, name, arguments, run_id):
    filter_keys = {"view", "module", "q", "due", "unread_only"} if name == "get_my_work" else set()
    if name not in NAMES or not isinstance(arguments, dict) or set(arguments) - {"factory_id", "resource_id", *filter_keys}:
        raise AssistantError("tool_invalid", "业务查询参数无效。")
    factory = arguments.get("factory_id")
    ident = arguments.get("resource_id")
    if not isinstance(factory, str) or len(factory) > 32 or (ident is not None and (not isinstance(ident, str) or len(ident) > 160)):
        raise AssistantError("tool_invalid", "业务查询范围无效。")
    with database.SessionLocal() as db:
        authorize(db, user, name, factory)
        scope = dict(factory_id=None if factory == "authorized" else factory, scope_label="本人全部授权范围" if factory == "authorized" else factory,
                     authorization="current_user")
        unknown = []
        if name == "get_my_work":
            from app.services.work_center import service as work
            filters = {k: v for k, v in arguments.items() if k in filter_keys}
            if any(not isinstance(v, str) or len(v) > 200 for k, v in filters.items() if k != "unread_only") or ("unread_only" in filters and not isinstance(filters["unread_only"], bool)):
                raise AssistantError("tool_invalid", "事项筛选参数无效。")
            value = work.snapshot(db, user, factory_scope=factory, limit=20, **filters)
            scope["filters"] = filters
            items = [work.detail(db, user, ident)] if ident else value["items"]
            if ident and factory != "authorized" and not any((items[0].get(k) or {}).get("id") == factory for k in ("source_factory", "execution_factory")):
                raise AssistantError("source_unavailable", "选中事项不在当前厂区。", 404)
            items = [{k: item.get(k) for k in ("id", "title", "summary", "lifecycle", "source_factory", "execution_factory", "due_at", "why_me", "verification_state")} for item in items]
            result = dict(authorized_summary={"scope_label": "本人全部授权范围（未应用厂区/视图筛选）", "values": value["summary"]},
                          filtered_total=value["query"]["filtered_total"], items=items, coverage=value["health"]["coverage"],
                          health=value["health"], truncated=value["next_cursor"] is not None)
            resources = [dict(module_id="work-center", resource_type="entry", resource_id=item["id"]) for item in items]
            unknown = ["未接入事项中心的业务不在本次统计内"]
        elif name == "get_injection_overview":
            from app.models.injection_scheduling import Demand
            from app.schemas.injection_scheduling import Query
            from app.services.injection_scheduling import queries
            payload = Query(factory_id=factory)
            conditions = queries.query_conditions(payload)
            if ident:
                conditions.append(Demand.id == ident)
                if not db.scalar(select(Demand.id).where(*conditions)):
                    raise AssistantError("source_unavailable", "选中需求不存在或不在当前厂区。", 404)
            count = lambda condition: db.scalar(select(func.count(Demand.id)).where(*conditions, condition)) or 0
            rows = db.scalars(select(Demand).where(*conditions).order_by(Demand.id).limit(20)).all()
            summary = queries.summary(db, payload)
            result = dict(reference_summary={"scope_label": "当前厂区全部需求", "values": summary},
                summary={"total_count": db.scalar(select(func.count(Demand.id)).where(*conditions)),
                    "wait_material_count": count(Demand.dispatch_state == "WAIT_MATERIAL"),
                    "held_count": count(Demand.dispatch_state != "READY"),
                    "remaining_material_kg": float(db.scalar(select(func.sum(Demand.remaining_material_kg)).where(*conditions)) or 0),
                    "remaining_material_unknown_count": count(Demand.remaining_material_kg.is_(None)),
                    "forecast_late_count": count(Demand.delivery_slack_hours < 0),
                    "forecast_unknown_count": count(Demand.delivery_slack_hours.is_(None)), "warehouse_shortage_kg": None},
                definitions={"held_count": "调度状态非READY的需求，不等于缺料", "remaining_material_kg": "预计剩余生产用料，不是仓库实际短缺量", "forecast_late_count": "预计排期超期风险，不是实际延期"},
                items=[dict(id=r.id, dispatch_state=r.dispatch_state, remaining_material_kg=float(r.remaining_material_kg) if r.remaining_material_kg is not None else None,
                    delivery_slack_hours=float(r.delivery_slack_hours) if r.delivery_slack_hours is not None else None) for r in rows])
            resources = [dict(module_id="injection-scheduling", resource_type="demand", resource_id=r.id) for r in rows]
            unknown = ["warehouse_shortage_kg", "actual_delivery_outcome"]
        else:
            from app.models.three_d_printing import ThreeDPrintingPrinter
            from app.services.three_d_printing import printer_out, network_health_snapshot
            network = network_health_snapshot(db)
            stmt = select(ThreeDPrintingPrinter).where(ThreeDPrintingPrinter.factory_id == factory)
            if ident:
                stmt = stmt.where(ThreeDPrintingPrinter.id == ident)
            rows = db.scalars(stmt.order_by(ThreeDPrintingPrinter.id).limit(30)).all()
            if ident and not rows:
                raise AssistantError("source_unavailable", "选中机台不存在。", 404)
            items = [printer_out(r, network_stale=network["configured"] and network["status"] != "healthy") for r in rows]
            result = dict(items=items, network_health={k: network.get(k) for k in ("configured", "status", "observed_at")}, limit=30,
                          notice="旧遥测不能判断设备当前物理状态；此查询不发设备命令")
            resources = [dict(module_id="three-d-printing", resource_type="printer", resource_id=r.id) for r in rows]
            unknown = ["physical_state"] if any(i["status_stale"] for i in items) else []
        as_of = now_iso()
        source = dict(kind="business", source_id=stable_id(run_id, name, factory, ident, as_of), run_id=run_id,
            title={"get_my_work": "我的工作", "get_injection_overview": "注塑排期", "get_printer_status": "3D机台状态"}[name],
            tool_name=name, resources=resources, scope=scope, as_of=as_of, data_mode="snapshot", unknown_fields=unknown,
            authorization_fingerprint=fingerprint(db, user))
        module, route = ROUTES[name]
        actions = [dict(type="open_record", label="查看" + source["title"], route_name=route, params={},
            query={**({"factory": factory} if factory != "authorized" else {}), **({"entry": ident} if ident and name == "get_my_work" else {})},
            resource=dict(module_id=module, resource_type="entry" if ident and name == "get_my_work" else "overview", resource_id=ident if ident and name == "get_my_work" else factory))]
        if name == "get_my_work" and not ident:
            actions.extend(dict(type="open_record", label="查看：" + item["title"], route_name=route, params={},
                query={"entry": item["id"], **({"factory": factory} if factory != "authorized" else {})},
                resource=dict(module_id=module, resource_type="entry", resource_id=item["id"])) for item in items[:3])
        return dict(scope=scope, as_of=as_of, data_mode="snapshot", unknown_fields=unknown, **result), source, actions


def visible(db, user, source):
    name = source.get("tool_name")
    factory = source.get("scope", {}).get("factory_id") or "authorized"
    authorize(db, user, name, factory)
    if source.get("authorization_fingerprint") != fingerprint(db, user):
        return False
    for resource in source.get("resources", []):
        ident = resource["resource_id"]
        if name == "get_my_work":
            from app.services.work_center.service import detail
            detail(db, user, ident)
        elif name == "get_injection_overview":
            from app.models.injection_scheduling import Demand
            if not db.scalar(select(Demand.id).where(Demand.id == ident, Demand.factory_id == factory)):
                return False
        else:
            from app.models.three_d_printing import ThreeDPrintingPrinter
            if not db.scalar(select(ThreeDPrintingPrinter.id).where(ThreeDPrintingPrinter.id == ident, ThreeDPrintingPrinter.factory_id == factory)):
                return False
    return True
