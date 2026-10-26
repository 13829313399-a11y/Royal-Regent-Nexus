"""Current-user capability checks, distinct from connector acceptance evidence.

No business query, session creation or provider probe belongs in this endpoint.
Each domain uses its existing authority and its own read-only DB session so one
unavailable domain cannot poison the checks for the others.
"""
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app import db as database
from app.core.config import settings
from app.core.time import business_now
from . import business, help_registry, registry


def _failure(error):
    if error.status_code == 403:
        return "forbidden", "当前账号在此厂区没有这项业务读取权限。"
    detail = error.detail if isinstance(error.detail, dict) else {}
    if detail.get("code") in {"module_disabled", "schema_not_ready"}:
        return "disabled", "此厂区的业务模块未启用或数据准备尚未完成。"
    if error.status_code in {400, 422}:
        return "not_connected", "此读取入口不支持当前范围，请选择适用厂区。"
    return "not_connected", "本次未能确认读取状态，请稍后刷新。"


def report(user, factory_id, module_id=None):
    grouped = defaultdict(list)
    for article in help_registry.articles():
        grouped[article.module_id].append(article)
    audience = "supplier" if help_registry.supplier_only(user) else "internal"
    module_ids = list(registry.BY_MODULE)
    module_ids.extend(sorted(set(grouped) - set(module_ids)))
    if module_id and module_id not in module_ids:
        module_ids.append(module_id)
    items = []
    for ident in module_ids:
        connector = registry.BY_MODULE.get(ident)
        articles = grouped[ident]
        visible = [a for a in articles if a.audience in {"all", audience}]
        applicable = [a for a in visible if not a.factory_ids or factory_id in a.factory_ids]
        guides = [a for a in applicable if a.status in {"verified", "partial"}]
        label = connector.label if connector else next((a.title for a in articles if a.kind == "overview"), "模块说明" if articles else "当前模块")
        state, reason = "not_connected", "尚未登记业务读取，也没有当前范围可用的操作说明。"
        if articles and not visible:
            state, reason = "forbidden", "当前身份不可查看此模块说明。"
        elif guides:
            state, reason = "guide_only", "只有已维护的操作说明，不能查询此模块的业务记录。"
        elif applicable:
            reason = "操作说明需要复核，当前没有可用的业务读取入口。"
        if connector and connector.callable:
            try:
                with database.SessionLocal() as db:
                    business.authorize(db, user, connector.tool_name, factory_id)
                state, reason = "business_read", connector.coverage_description or "按当前账号与厂区权限只读查询。"
            except HTTPException as error:
                state, reason = _failure(error)
            except SQLAlchemyError:
                state, reason = "not_connected", "本次未能确认读取状态，请稍后刷新。"
        if not settings.assistant_enabled and state != "forbidden":
            state, reason = "disabled", "曜灵当前未启用。"
        items.append(dict(module_id=ident, label=label, state=state, reason=reason,
            read_only=True, guide_count=len(guides),
            # Permission to call never promotes implemented_unverified to connected.
            verification=connector.coverage_state if connector else "not_registered"))
    return dict(factory_id=factory_id, checked_at=business_now().isoformat(),
        catalog_scope="registered_modules", items=items)
