"""Private work queues; confirmed ledger data retains its factory-wide access."""
from copy import deepcopy
from sqlalchemy import inspect, select, or_
from app.models.auth import AuthUser
from app.models.indonesia_materials import IndonesiaMaterialRecord as Record, IndonesiaMaterialCommand as Receipt
from app.services.auth import authorization_decision, scope_matches, time_window_is_active, build_auth_context
from app.services.indonesia_material_calculations import require

MANAGER_ROLES = {'position_sales_manager', 'position_sales_supervisor'}


def epoch(user):
    return (user.identity or {}).get('employment_epoch', 1)


def person(user):
    return dict(id=user.id, username=user.username, name=user.display_name or user.username, employment_epoch=epoch(user))


def ownership(user):
    return dict(uploader=person(user), assignee=person(user), transfers=[])


def pending(row):
    return row.kind in {'import', 'shipment'} and row.data.get('status') != 'confirmed'


def manager(user, factory):
    decisions = [authorization_decision(user, 'indonesia_material:' + action, factory, 'sales-business') for action in ('read', 'write')]
    if not all(item[0] for item in decisions):
        return False
    return decisions[1][1] == 'superadmin' or any(
        grant.role_id in MANAGER_ROLES and scope_matches(grant.factory_id, grant.department, factory, 'sales-business')
        and (grant.factory_ceiling is None or factory in grant.factory_ceiling)
        and time_window_is_active(grant.valid_from, grant.valid_until) for grant in user.grants)


def eligible(user, factory):
    return all(authorization_decision(user, 'indonesia_material:' + action, factory, 'sales-business')[0] for action in ('read', 'write'))


def target_user(db, user_id, factory):
    account = db.get(AuthUser, user_id)
    require(account is not None and account.status == 'active', '接收账号不可用，请重新选择负责人', 422)
    user = build_auth_context(db, account)
    require(eligible(user, factory), '接收账号没有当前厂区的送印尼物料维护权限', 422)
    return user


def assignees(db, user, factory, search=''):
    require(manager(user, factory), '仅当前厂区业务主管或管理员可以转交', 403)
    query = select(AuthUser).where(AuthUser.status == 'active').order_by(AuthUser.id)
    if search.strip():
        text = search.strip()
        query = query.where(or_(AuthUser.username.contains(text, autoescape=True), AuthUser.display_name.contains(text, autoescape=True)))
    result = []
    # Only return people eligible for this factory, never the wider account directory.
    scanned = list(db.scalars(query.limit(501)))
    for account in scanned[:500]:
        context = build_auth_context(db, account)
        if eligible(context, factory):
            result.append(person(context))
            if len(result) == 50:
                break
    return dict(people=result, refine_search=len(scanned) > 500 or len(result) == 50)


class Access:
    def __init__(self, db, user, factory):
        self.db, self.user, self.factory = db, user, factory
        self.is_manager = manager(user, factory)
        self._legacy = None
        self._people = {user.id: person(user)}

    def legacy_person(self, user_id):
        if not user_id:
            return None
        if user_id not in self._people:
            account = self.db.get(AuthUser, user_id) if inspect(self.db.connection()).has_table(AuthUser.__tablename__) else None
            self._people[user_id] = dict(id=user_id, name=(account.display_name or account.username) if account else user_id,
                                         username=account.username if account else '', employment_epoch=1)
        # Historical records cannot grant a rehired identity access to the old employee's work.
        return dict(self._people[user_id], employment_epoch=1)

    def info(self, row):
        if row.data.get('_ownership'):
            return deepcopy(row.data['_ownership'])
        creator = row.data.get('provided_by')
        if not creator and row.kind == 'shipment':
            if self._legacy is None:
                self._legacy = {}
                receipts = self.db.scalars(select(Receipt).where(Receipt.factory_id == self.factory,
                    Receipt.action.in_(['shipment_save', 'warehouse_import_confirm'])).order_by(Receipt.created_at, Receipt.operation_id))
                for receipt in receipts:
                    for change in receipt.changes:
                        after = change.get('after') or {}
                        if not change.get('before') and after.get('kind') == 'shipment':
                            self._legacy.setdefault(after['id'], receipt.actor_id)
            creator = self._legacy.get(row.id)
        original = self.legacy_person(creator)
        return dict(uploader=original, assignee=original, transfers=[])

    def owns(self, row):
        assignee = self.info(row).get('assignee') or {}
        return assignee.get('id') == self.user.id and assignee.get('employment_epoch', 1) == epoch(self.user)

    def visible(self, row):
        # Original uploads can contain skipped/rejected lines even after confirmation.
        # Share their formal products/orders/receipts, never the whole private source file.
        return (row.kind != 'import' and not pending(row)) or self.is_manager or self.owns(row)

    def require(self, row):
        require(self.visible(row), '该待办不存在或已转交其他跟客，请刷新列表；本机草稿仍保留', 404)

    def present(self, row):
        from app.services.indonesia_materials import view
        result = view(row)
        if row.kind in {'import', 'shipment'}:
            result['responsibility'] = dict(self.info(row), can_transfer=pending(row) and self.is_manager)
        if row.kind == 'import' and 'shipment_ids' in result['data']:
            result['data']['shipment_ids'] = [id for id in result['data']['shipment_ids']
                if (shipment := self.db.get(Record, id)) is not None and shipment.factory_id == self.factory and self.visible(shipment)]
        return result

    def transfer(self, ledger, body):
        from app.schemas.indonesia_materials import Transfer
        from app.services.indonesia_materials import now_text
        require(self.is_manager, '仅当前厂区业务主管或管理员可以转交', 403)
        payload = Transfer.model_validate(body.data)
        row = self.db.get(Record, body.entity_id) if body.entity_id else None
        require(row is not None and row.factory_id == self.factory and pending(row), '请选择尚未确认的导入或出货草稿', 422)
        require(row.version == body.expected_version, '记录已更新，请刷新后重新转交', 409)
        new_owner = person(target_user(self.db, payload.assignee_id, self.factory))
        info = self.info(row)
        require(info.get('assignee') != new_owner, '该记录已由所选人员负责', 422)
        info['transfers'].append(dict(previous=info.get('assignee'), assignee=new_owner, by=person(self.user),
                                      at=now_text(), reason=payload.reason))
        info['assignee'] = new_owner
        data = deepcopy(row.data)
        data['_ownership'] = info
        return ledger.save(row.kind, data, row)
