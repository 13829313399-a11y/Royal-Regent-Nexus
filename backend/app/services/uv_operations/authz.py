from datetime import UTC, datetime
from decimal import Decimal
from sqlalchemy import inspect
from weakref import WeakKeyDictionary
from threading import Lock
from app.core.config import settings
from app.models import uv_operations as m
from app.services.auth import authorization_decision
from . import common as c

_schemas=WeakKeyDictionary()
_schema_lock=Lock()


def allowed(user, action):
    return authorization_decision(user, "uv_ops:" + action, m.FACTORY, "production")[0]


def authorize(user, factory, *actions):
    c.require(factory == m.FACTORY, "factory_required", "UV 打印仅支持明确选择华康 A 厂区", 422)
    for action in {"read", *actions}:
        c.require(allowed(user, action), "permission_denied", "没有当前厂区 UV 模块的相应权限", 403)
    c.require(settings.uv_ops_enabled, "module_disabled", "UV 打印模块尚未启用，请联系管理员完成迁移与配置", 503)


def ready(db):
    # Cache only immutable schema readiness, never permissions or business data.
    if db.bind not in _schemas:
        with _schema_lock:
            if db.bind not in _schemas:
                inspector=inspect(db.connection())
                c.require(inspector.has_table('uv_ops_settings') and inspector.has_table('uv_ops_schedule_blocks'), 'schema_not_ready', 'UV 模块尚未迁移，业务库不会自动建表', 503)
                c.require('batch_id' in {x['name'] for x in inspector.get_columns('uv_ops_schedule_blocks')},'schema_not_ready','UV 批次排程需要显式迁移至 20260929_0127',503)
                c.require(inspector.has_table('uv_ops_executions') and inspector.has_table('uv_ops_reversals') and 'active_key' in {x['name'] for x in inspector.get_columns('uv_ops_wage_accruals')}, 'schema_not_ready', 'UV 纠错与执行凭证需要显式迁移至 20260929_0127', 503)
                _schemas[db.bind]=True
    c.require(db.scalar(c.query(m.UvOpsSettings)) is not None, "schema_not_ready", "UV 模块配置尚未初始化", 503)


# Only these exact DTO fields carry sensitive values. New DTOs must explicitly
# extend this policy and its contract tests; audit rows never contain payloads.
COST_FIELDS = frozenset({"cost_price_snapshot", "cost_value", "cost_amount", "cost_revenue", "cost_total", "cost_margin", "cost_unit", "achievable_cost_unit", "cost_by_currency", "cost_missing", "price_policies", "cost_allocations"})
PAYROLL_FIELDS = frozenset({"payroll_policy_snapshot", "payroll_amount", "payroll_weight_seconds", "payroll_evidence", "payroll_total", "wages", "wage_policies", "wage_allocations", "cost_total", "cost_margin"})


def project(value, user):
    excluded = (set() if allowed(user, "cost_read") else COST_FIELDS) | (set() if allowed(user, "payroll_read") else PAYROLL_FIELDS)
    def visit(item):
        if isinstance(item, dict):
            return {key: visit(child) for key, child in item.items() if key not in excluded}
        if isinstance(item, (list, tuple)):
            return [visit(child) for child in item]
        if isinstance(item, Decimal):
            return format(item, 'f')
        if isinstance(item, datetime):
            return c.ts(item)
        return item
    return visit(value)


def envelope(db, user, data, *, coverage=None, pagination=None, warnings=None, view_revision=None, as_of=None):
    config = db.scalar(c.query(m.UvOpsSettings))
    result = dict(data=project(data, user), meta=dict(factory_id=m.FACTORY, as_of=as_of or datetime.now(UTC).isoformat(), data_mode=config.data_mode, authorization_version=user.authorization_version, view_revision=c.revision(db) if view_revision is None else view_revision, coverage=coverage or dict(state="unknown", unmatched_runs=None, unconfirmed_output=None, missing_cost_records=None), warnings=warnings or []))
    if pagination is not None:
        result["pagination"] = pagination
    return result
