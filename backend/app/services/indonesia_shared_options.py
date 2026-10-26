"""Shared choices only. Never grants access to another factory's business ledger."""
from copy import deepcopy
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from app.models.indonesia_materials import IndonesiaMaterialSharedOption as SharedOption
from app.models.indonesia_materials import IndonesiaMaterialRecord as Record, IndonesiaMaterialCommand as Receipt
from app.services import indonesia_materials as ledger
from app.services.auth import authorization_decision, scope_matches, time_window_is_active
from app.services.indonesia_material_options import Option, OptionIdentity, defaults, option_key
from app.services.indonesia_material_calculations import require, number
from app.services.identity_policy import lock_mutation
from app.services.transaction_lock import lock_transaction

SCOPE = 'shared-options'
MANAGER_ROLES = {'position_sales_manager', 'position_sales_supervisor'}


def factories(user, action):
    if action == 'write':
        return sorted(factory for factory in ledger.FACTORIES if all(authorization_decision(user, 'indonesia_material:' + permission, factory, 'sales-business')[0] for permission in ('read', 'write')))
    return sorted(factory for factory in ledger.FACTORIES if ledger.allowed(user, factory, 'read') and ledger.allowed(user, factory, action))


def manager(user):
    for factory in factories(user, 'write'):
        if authorization_decision(user, 'indonesia_material:write', factory, 'sales-business')[1] == 'superadmin':
            return True
        if any(grant.role_id in MANAGER_ROLES and scope_matches(grant.factory_id, grant.department, factory, 'sales-business')
               and (grant.factory_ceiling is None or factory in grant.factory_ceiling)
               and time_window_is_active(grant.valid_from, grant.valid_until) for grant in user.grants):
            return True
    return False


def records(db):
    return list(db.scalars(select(SharedOption).order_by(SharedOption.id)))


def view(row):
    return dict(ledger.view(row), scope=SCOPE)


def workspace(db, user):
    require(factories(user, 'read'), '没有送印尼物料查看权限', 403)
    ledger.ready(db)
    rows = records(db)
    require(len(rows) <= 5000, '共用选项超过容量，请联系管理员扩展分页', 409)
    permissions = ['read'] + (['write'] if factories(user, 'write') else []) + (['options_manage'] if manager(user) else [])
    return dict(records=[view(row) for row in rows], board=[], option_defaults=defaults(), permissions=permissions)


def referenced(db, data):
    # Check globally but expose no other factory's private rows or customer names.
    field = {'category': 'category', 'customs_unit': 'customs_unit', 'unit': 'unit', 'usage': 'usage',
             'currency': 'currency', 'supplier': 'supplier', 'export_company': 'export_company'}[data['group']]
    def contains(value):
        if isinstance(value, list):
            return any(contains(item) for item in value)
        if not isinstance(value, dict):
            return False
        return str(value.get(field, '')).strip().casefold() == data['value'].casefold() or any(contains(item) for item in value.values())
    return any(contains(row.data) for row in db.scalars(select(Record)))


def run_command(db, user, body, *, refresh_user):
    require(body.factory_id == SCOPE and body.action in {'option_save', 'option_delete', 'option_restore'}, '请选择共用基础选项操作', 422)
    require(factories(user, 'write'), '没有共用基础选项维护权限', 403)
    ledger.ready(db)
    fingerprint = ledger.digest(body.model_dump(mode='json'))
    try:
        lock_mutation(db)
        lock_transaction(db, 'indonesia-shared-options', SCOPE)
        current = refresh_user()
        require(current.id == user.id, '账号身份已变化，请重新核对操作', 401)
        require(factories(current, 'write'), '没有共用基础选项维护权限', 403)
        previous = db.get(Receipt, body.operation_id)
        if previous:
            require(previous.actor_id == current.id and previous.factory_id == SCOPE and previous.fingerprint == fingerprint, '操作编号已用于不同请求')
            return previous.result
        row = db.get(SharedOption, body.entity_id) if body.entity_id else None
        require(not body.entity_id or row is not None, '共用选项不存在', 404)
        require((row.version if row else 0) == body.expected_version, '共用选项已被更新，请重新核对')
        before = view(row) if row else None
        if body.action == 'option_save':
            data = Option.model_validate(body.data).model_dump(mode='json')
            data['value'] = data['value'].upper() if data['group'] in {'currency', 'customs_unit'} else data['value'].strip()
            if data['group'] != 'customs_unit':
                data.update(billing_basis='quantity', kg_per_unit='1')
            require(not row or not row.data.get('deleted'), '请先恢复已删除的共用选项', 404)
            require(not row or (row.data['group'], row.data['value']) == (data['group'], data['value']), '选项分类及名称不能覆盖修改，请新增正确名称', 422)
            protected = data['status'] != 'active' if row is None else data['status'] != row.data['status']
            if data['group'] == 'customs_unit':
                initial = next((item for item in defaults() if option_key(item['group'], item['value']) == option_key(data['group'], data['value'])), None)
                original = row.data if row else initial or dict(billing_basis='quantity', kg_per_unit='1')
                protected |= data['billing_basis'] != original['billing_basis'] or number(data['kg_per_unit']) != number(original['kg_per_unit'])
            require(not protected or manager(current), '启停及换算规则调整仅限有模块维护权限的业务主管或管理员', 403)
            if row and 'legacy_sources' in row.data:
                data['legacy_sources'] = deepcopy(row.data['legacy_sources'])
        else:
            require(manager(current), '删除和恢复共用选项仅限有模块维护权限的业务主管或管理员', 403)
            if row is None and body.action == 'option_delete':
                identity = OptionIdentity.model_validate(body.data).model_dump(mode='json')
                data = next((item for item in defaults() if option_key(item['group'], item['value']) == option_key(identity['group'], identity['value'])), None)
                require(data is not None, '请选择已存在的共用选项', 422)
            else:
                require(row is not None and not body.data, '删除和恢复须选择原选项及版本', 422)
                data = deepcopy(row.data)
            deleting = body.action == 'option_delete'
            require(bool(data.get('deleted')) != deleting, '共用选项状态已变化')
            require(not deleting or not referenced(db, data), '该选项已被使用，不能删除；可停用以保留历史资料')
            data.update(deleted=deleting, deleted_by=current.id if deleting else None, deleted_at=ledger.now_text() if deleting else None)
        data.update(updated_by=current.id, authority_factory=factories(current, 'write')[0])
        if row is None:
            row = SharedOption(id=str(uuid4()), business_key=option_key(data['group'], data['value']), version=0)
            db.add(row)
        row.data = data
        row.version += 1
        row.updated_at = ledger.now_text()
        db.flush()
        result = dict(record=view(row))
        db.add(Receipt(operation_id=body.operation_id, factory_id=SCOPE, actor_id=current.id, action=body.action,
                       fingerprint=fingerprint, changes=[dict(before=before, after=view(row))], result=result, created_at=ledger.now_text()))
        db.commit()
        return result
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        from fastapi import HTTPException
        raise HTTPException(409, '共用选项重复或正被其他人员修改，请重新读取核对') from exc
    except Exception:
        db.rollback()
        raise
