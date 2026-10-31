"""Canonical ownership guard shared by quick and legacy asset entry points."""
import os
from dataclasses import replace
from fastapi import HTTPException
from app.services.auth import authorization_decision
from app.core.config import settings

DEPARTMENTS = ('sales-business','pmc-warehouse','carton')


def enabled():
    return os.getenv('CARTON_ASSET_V1_ENABLED',str(settings.carton_asset_v1_enabled)).lower() == 'true'


def writes():
    if not enabled() or os.getenv('CARTON_ASSET_V1_WRITES_ENABLED',str(settings.carton_asset_v1_writes_enabled)).lower() != 'true':
        raise HTTPException(403,'快速资料写入已关闭；现有归属和资料仍保留')


def allowed(user, factory, department, action='read'):
    if department in DEPARTMENTS:
        # Global asset-only overrides are the external supplier mapping. They
        # must never establish an internal department identity. Explicit denies
        # and canonical role/assignment checks remain authoritative.
        user=replace(user,overrides=tuple(x for x in user.overrides if not (
            x.permission_code.startswith('carton_asset:') and x.effect=='allow' and x.department=='*')))
    return authorization_decision(user,'carton_asset:'+action,factory,department)[0]


def internal_scope(user,factory,action='read'):
    from app.services.carton_procurement import require_carton_factory
    factory=require_carton_factory(factory)
    if not any(allowed(user,factory,d,action) for d in DEPARTMENTS):
        raise HTTPException(403,'没有当前厂区部门资料权限')
    return factory


def owner(db,user,factory,department=None,*,supplier=False):
    if supplier:
        from app.services.carton_supplier_portal import supplier_access
        row=supplier_access(db,user,factory,'carton_supplier:edit')
        if department not in (None,'supplier') or not allowed(user,factory,'supplier','manage'):
            raise HTTPException(403,'没有东康自有资料维护权限')
        return 'supplier',row.id
    choices=[d for d in DEPARTMENTS if allowed(user,factory,d,'manage')]
    if department is None:
        if len(choices)!=1: raise HTTPException(422,'请选择本次资料归属部门；多部门账号不能自动归属')
        department=choices[0]
    if department not in choices: raise HTTPException(403,'资料归属部门不在当前有效授权内')
    return department,None


def managed(asset):
    return bool(asset.owner_department) or asset.asset_purpose=='EVIDENCE' or asset.kind=='text' or enabled()


def ensure(db,user,asset,*,write=False,confirm=False,library=False,supplier=None,view_factory=None,collaborate=False):
    if asset.recognition_source=='materials_folder': raise HTTPException(404,'请从原订单资料记录查阅')
    if asset.is_archived: raise HTTPException(404,'资料已归档')
    if view_factory and view_factory!=asset.factory_id and asset.owner_department!='supplier':
        raise HTTPException(404,'资料不属于当前厂区')
    if not managed(asset): return
    if supplier is None and view_factory in (None,asset.factory_id):supplier=external_actor(db,user,asset)
    action='confirm' if confirm else 'manage' if write else 'read'
    department=asset.owner_department
    if supplier is not None:
        from app.services.carton_supplier_portal import supplier_access
        current=supplier_access(db,user,asset.factory_id,'carton_supplier:edit' if write else 'carton_supplier:read')
        if current.id!=supplier.id or asset.asset_purpose=='EVIDENCE': raise HTTPException(404,'资料不可访问')
        if department is None: raise HTTPException(404,'历史资料缺少可信归属')
        own=department=='supplier' and asset.owner_supplier_id==current.id
        if write and not own: raise HTTPException(403,'不能修改其他部门原件')
        if own and allowed(user,asset.factory_id,'supplier','manage' if write or confirm else 'read'):
            if write: writes()
            return
        if not write and not confirm and allowed(user,asset.factory_id,'supplier','read'):
            from app.services.carton_asset_targets import shared_with_supplier
            if shared_with_supplier(db,asset,current): return
        raise HTTPException(404,'资料不可访问')
    if asset.asset_purpose=='MATERIAL':
        from app.services.carton_asset_visibility import internal_read
        factory=view_factory or asset.factory_id
        internal_read(db,user,asset,factory)
        if write or confirm:
            if not collaborate and not confirm:
                own_department=department in DEPARTMENTS and allowed(user,asset.factory_id,department,'manage')
                legacy_owner=department is None and (asset.created_by==user.id or authorization_decision(user,'system:user_manage',asset.factory_id,'system')[0])
                if not own_department and not legacy_owner:
                    raise HTTPException(403,'共享资料可更新状态和关联订单，原件维护仍由上传部门负责')
            if confirm:
                if not any(can_confirm(user,factory,d) for d in DEPARTMENTS):
                    raise HTTPException(403,'没有资料状态确认权限')
            else:
                internal_scope(user,factory,'manage')
            writes()
        return
    if department is None:
        # Historic rows have no trustworthy department. Creator is not a grant.
        if not internal_scope(user,asset.factory_id,action): raise HTTPException(403,'无资料权限')
        admin=authorization_decision(user,'system:user_manage',asset.factory_id,'system')[0]
        if not admin and asset.created_by!=user.id: raise HTTPException(404,'历史资料仅原上传人或授权管理员可见')
        if write: writes()
        return
    if department in DEPARTMENTS and allowed(user,asset.factory_id,department,action):
        if write or confirm: writes()
        return
    if not write and not confirm and not library and asset.asset_purpose=='MATERIAL':
        internal_scope(user,asset.factory_id)
        from app.services.carton_asset_targets import shared_with_internal
        if shared_with_internal(db,user,asset): return
    raise HTTPException(403,'只能管理本部门资料；其他部门普通资料须经关联目标授权读取')


def can_confirm(user,factory,department):
    decision=authorization_decision(user,'carton_asset:confirm',factory,department)
    if not decision[0] and decision[1] in {'user_override','inactive_permission','account_unavailable'}:return False
    return allowed(user,factory,department,'confirm') or allowed(user,factory,department,'manage')


def visible(db,user,asset,**kwargs):
    try: ensure(db,user,asset,**kwargs); return True
    except HTTPException: return False


def legacy(db,user,asset,*,department=None,supplier_id=None):
    """Called before every legacy producer writes a source, when rollout is on."""
    if not enabled():return
    writes()
    chosen,identifier=owner(db,user,asset.factory_id,department,supplier=bool(supplier_id))
    if supplier_id and identifier!=supplier_id:raise HTTPException(403,'供应商归属不符')
    asset.owner_department=chosen;asset.owner_supplier_id=identifier;asset.asset_purpose='MATERIAL'


def external_actor(db,user,asset):
    if any(allowed(user,asset.factory_id,d) for d in DEPARTMENTS):return None
    from app.services.carton_supplier_portal import supplier_access
    try:return supplier_access(db,user,asset.factory_id)
    except HTTPException:return None
