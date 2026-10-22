"""Line-scoped, immutable production material for sample and miscellaneous orders."""
from fastapi import HTTPException
from sqlalchemy import select
from app.models.carton_mark import CartonMarkAsset
from app.models.carton_special_requests import SpecialLine, SpecialAttachment
from app.services import carton_special_requests as special
from app.services.carton_mark_library import CARTON_MARK_READ_DEPARTMENTS
from app.services.auth import authorization_decision


def require_library(user, factory):
    if not any(authorization_decision(user, "carton_mark:read", factory, dept)[0]
               for dept in CARTON_MARK_READ_DEPARTMENTS):
        raise HTTPException(403, "没有本厂箱唛资料库读取权限")


def associated_files(db, user, factory, *, external=False, request_ids=None):
    from app.services import carton_mark_sharing as sharing, carton_mark_assets as assets
    states = sharing.states(db, factory)
    ids = [identifier for identifier, state in states.items() if any(
        request_ids is None or x['order_id'] in request_ids for x in state['special_orders'])]
    if not ids: return {}
    try:
        if external:
            from app.services.carton_supplier_portal import supplier_mark_assets
            values = supplier_mark_assets(db, user, factory, asset_ids=ids)
        else:
            require_library(user, factory)
            orders = assets.available_orders(db, factory)
            values = [x.model_dump() for x in sharing.filter_internal(db, user, [assets.asset_out(asset, orders)
                for asset in db.scalars(select(CartonMarkAsset).where(CartonMarkAsset.factory_id == factory,
                    CartonMarkAsset.is_archived.is_(False), CartonMarkAsset.id.in_(ids)))])]
    except HTTPException as exc:
        if exc.status_code != 403: raise
        return {}
    result = {}
    for value in values:
        for link in value.get('associations', []):
            if link['order_kind'] == 'REGULAR': continue
            if request_ids is not None and link['order_id'] not in request_ids: continue
            result.setdefault(link['order_id'], []).append(dict(id=value['id'], file_name=value['file_name'],
                revision=value['revision'], kind=value['kind'], line_id=link.get('line_id', '')))
    return result


def options(db, user, factory, request_id='', external=False):
    target = special.access(db, user, factory, request_id or None, external=external)
    if external:
        from app.services.carton_supplier_portal import _supplier_mark_assets
        candidates = [asset for asset, _ in _supplier_mark_assets(db, user, factory)]
    else:
        require_library(user, factory)
        candidates = list(db.scalars(select(CartonMarkAsset).where(CartonMarkAsset.factory_id == factory,
            CartonMarkAsset.is_archived.is_(False)).order_by(CartonMarkAsset.file_name, CartonMarkAsset.id)))
    from app.services import carton_mark_asset_workflow as lifecycle, carton_mark_sharing as sharing
    allowed = []
    for asset in candidates:
        try:
            if not external:
                sharing.ensure_asset_access(db, user, asset)
                # This picker is a new customer-scoped entry point, including
                # legacy sources whose original library keeps its old rules.
                for order in sharing.related_orders(db, asset):
                    sharing.ensure_customer(db, user, order)
            if target:
                validate_asset_target(db, asset, target)
        except HTTPException:
            continue
        allowed.append(asset)
    candidates = allowed
    return [{"id": row.id, "file_name": row.file_name, "revision": row.revision,
             "contract_number": row.contract_number, "kind": row.kind}
            for row in candidates if lifecycle.current(db, row).status != 'HISTORY']


def validate_asset_target(db, asset, row):
    from app.services import carton_mark_sharing as sharing, carton_mark_assets as assets
    audience = sharing.current(db, asset)
    if audience['sharing_mode'] == 'INTERNAL':
        raise HTTPException(422, '此资料仅内部可见，请先共享给对应供应商')
    if audience['sharing_mode'] == 'SUPPLIER' and audience['shared_supplier_id'] != row.supplier_id:
        raise HTTPException(422, '此资料共享给其他供应商，请选择本单供应商的资料')
    matches = sharing.related_orders(db, asset)
    if any(o.supplier_id != row.supplier_id for o in matches):
        raise HTTPException(422, '此资料属于其他供应商订单')
    if any(assets.identity(o.customer_code) != assets.identity(row.customer_code) for o in matches):
        raise HTTPException(422, '此资料属于其他客户，请核实箱唛')
    from app.models.carton_special_requests import SpecialRequest
    for link in audience['special_orders']:
        linked = db.get(SpecialRequest, link['order_id'])
        if linked and (linked.supplier_id != row.supplier_id or assets.identity(linked.customer_code) != assets.identity(row.customer_code)):
            raise HTTPException(422, '此资料属于其他供应商或客户的订单，请核实后分别维护')
    from app.services import carton_mark_asset_workflow as lifecycle
    if lifecycle.current(db, asset).status == 'HISTORY':
        raise HTTPException(409, '历史稿不能直接用于新订单，请选择当前版本')


def link_event(db, user, asset, row, line, attachment_id, confirmed=False):
    from app.services import carton_mark_sharing as sharing, carton_mark_assets as assets
    assets.audit(db, user, asset, sharing.SPECIAL, dict(order_id=row.id, order_no=row.request_no,
        order_kind='SAMPLE' if row.kind == 'SAMPLE' else 'MISC', line_id=line.id if line else '',
        attachment_id=attachment_id, confirmed=confirmed, supplier_id=row.supplier_id,
        customer_code=row.customer_code))


def publish_attachment(db, user, row, paper, attachment, external=False):
    """Keep the execution snapshot immutable; library copy has its own lifecycle."""
    from pathlib import Path
    from app.services import carton_mark_sharing as sharing, carton_mark_assets as assets
    from app.services import carton_mark_asset_workflow as lifecycle
    from app.schemas.carton_mark import CartonMarkAssetUploadOptions
    suffix = Path(attachment.filename).suffix.lower()
    kind = 'image' if suffix in assets.IMAGE_CONTENT_TYPES else 'pdf' if suffix == '.pdf' else 'excel' if suffix in {'.xls', '.xlsx', '.xlsm'} else None
    if kind is None: return None  # Non-mark Word reference evidence remains on the order.
    asset = CartonMarkAsset(id=special.uid('CMA-'), factory_id=row.factory_id, file_name=attachment.filename,
        kind=kind, content_type=attachment.media_type, size_bytes=attachment.size, sha256=attachment.sha256,
        content=attachment.content, contract_number='', recognition_source='manual_orders', candidates_json='[]',
        warning='', revision=1, is_archived=False, created_by=user.id, created_by_name=user.display_name,
        created_at=attachment.created_at, updated_at=attachment.created_at)
    db.add(asset); db.flush()
    lifecycle.initialize(db, user, asset, CartonMarkAssetUploadOptions(status='PENDING'))
    sharing.record(db, user, asset, 'SUPPLIER', row.supplier_id)
    link_event(db, user, asset, row, paper, attachment.id)
    assets.audit(db, user, asset, 'CARTON_MARK_ASSET_CREATED', dict(sha256=asset.sha256,
        source_attachment_id=attachment.id, special_order_id=row.id))
    return asset


def _mark_evidence(db, user, identifier, line_id, payload, *, external=False):
    user = special.locked_actor(db, user, payload.factory_id)
    row = special.access(db, user, payload.factory_id, identifier, external=external)
    if not special.flags(db, user, row, external)['can_attach']:
        raise HTTPException(403, '当前订单不可维护资料')
    action = 'MARK_PROPOSE' if external else 'MARK_SET'
    digest, saved = special.replay(db, user, payload, action, identifier, line_id)
    if saved: return saved
    special.require_revision(row, payload)
    line = db.get(SpecialLine, line_id)
    if not line or line.request_id != row.id or line.factory_id != row.factory_id:
        raise HTTPException(404, '纸品不存在')
    asset = None
    if payload.mark_mode == 'EXISTING':
        if external:
            from app.services.carton_supplier_portal import supplier_mark_asset_document
            asset = supplier_mark_asset_document(db, user, row.factory_id, payload.asset_id)
        else:
            require_library(user, row.factory_id)
            asset = db.get(CartonMarkAsset, payload.asset_id)
            if not asset or asset.factory_id != row.factory_id or asset.is_archived:
                raise HTTPException(404, '资料不存在或无权访问')
            from app.services.carton_mark_sharing import ensure_asset_access
            ensure_asset_access(db, user, asset)
        if asset.revision != payload.asset_revision: raise HTTPException(409, '资料版本已变化，请刷新')
        validate_asset_target(db, asset, row)
        if asset.size_bytes > 10 * 1024 * 1024: raise HTTPException(422, '订单附件不能超过 10 MiB；大文件请从资料库直接关联')
        file = SpecialAttachment(id=special.uid('CSA-SP-'), factory_id=row.factory_id, request_id=row.id,
            line_id=line.id, role='DRAFT', filename=asset.file_name, media_type=asset.content_type,
            sha256=asset.sha256, size=asset.size_bytes, content=asset.content, created_by=user.id,
            created_at=special.core.now_text(), version=special.next_attachment_version(db, row))
        db.add(file)
    elif payload.mark_mode == 'UPLOAD':
        file = db.get(SpecialAttachment, payload.attachment_id)
        if not file or file.factory_id != row.factory_id or file.request_id != row.id or file.line_id not in {'', line.id}:
            raise HTTPException(404, '附件必须属于本订单对应纸品')
        from app.services import carton_mark_sharing as sharing
        source_id = next((key for key, state in sharing.states(db, row.factory_id).items()
            if any(x['attachment_id'] == file.id for x in state['special_orders'])), '')
        asset = db.get(CartonMarkAsset, source_id) if source_id else None
        if asset:
            if asset.is_archived: raise HTTPException(409, '源资料已归档，请核实')
            validate_asset_target(db, asset, row)
    else:
        if payload.asset_id or payload.attachment_id: raise HTTPException(422, '资料参数不一致')
        # Legacy NONE/PENDING are optional informational input, not a printing
        # decision. In particular they cannot erase an old confirmed manifest.
        file = None
    if asset:
        from app.services.carton_mark_asset_workflow import bump
        bump(db, asset, asset.revision)
        link_event(db, user, asset, row, line, file.id)
    # File evidence does not change line marks, execution version, price or promise.
    # The response and replay snapshot must include the evidence just appended.
    db.flush()
    return special.finish(db, user, payload, row, action, digest, external=external)


def propose_mark(db, user, identifier, line_id, payload):
    return _mark_evidence(db, user, identifier, line_id, payload, external=True)


def set_mark(db, user, identifier, line_id, payload):
    return _mark_evidence(db, user, identifier, line_id, payload)
