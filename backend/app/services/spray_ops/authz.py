"""Shared canonical spray authority for native APIs and private readers."""
from app.core.config import settings
from app.models import spray_ops as m
from app.services.auth import authorization_decision
from sqlalchemy import inspect
from . import common as c


def allowed(user, factory, action):
    return authorization_decision(user, 'spray_ops:' + action, factory, 'production')[0]


def authorize(user, factory, *actions):
    c.require(factory in m.FACTORIES, 'factory_required', '请选择华兴、华登、华康A或华康B的明确工厂', 422)
    for action in {'read', *actions}:
        c.require(allowed(user, factory, action), 'permission_denied', '没有当前工厂喷油模块的相应权限', 403)
    c.require(settings.spray_ops_enabled, 'module_disabled', '喷油部生产管理尚未启用', 503)


def ready(db, factory):
    c.require(inspect(db.connection()).has_table(m.SprayOpsFactory.__tablename__),
              'schema_not_ready', '喷油模块尚未迁移', 503)
    gate = db.get(m.SprayOpsFactory, factory)
    c.require(gate is not None, 'schema_not_ready', '喷油模块尚未迁移', 503)
    return gate
