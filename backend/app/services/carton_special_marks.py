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
    lifecycle.initialize(db, user, asset, CartonMarkAssetUploadOptions(status='READY' if attachment.role == 'CONFIRMED' else 'PENDING'))
    sharing.record(db, user, asset, 'SUPPLIER', row.supplier_id)
    link_event(db, user, asset, row, paper, attachment.id, attachment.role == 'CONFIRMED')
    assets.audit(db, user, asset, 'CARTON_MARK_ASSET_CREATED', dict(sha256=asset.sha256,
        source_attachment_id=attachment.id, special_order_id=row.id))
    return asset


def propose_mark(db, user, identifier, line_id, payload):
    user = special.locked_actor(db, user, payload.factory_id)
    row = special.access(db, user, payload.factory_id, identifier, external=True)
    if not special.flags(db, user, row, True)['can_attach']:
        raise HTTPException(403, '当前订单不可提交箱唛')
    if payload.mark_mode != 'EXISTING': raise HTTPException(422, '供应商只能选择已有资料作为待确认稿')
    digest, saved = special.replay(db, user, payload, 'MARK_PROPOSE', identifier, line_id)
    if saved: return saved
    special.require_revision(row, payload)
    line = db.get(SpecialLine, line_id)
    if not line or line.request_id != row.id or line.factory_id != row.factory_id: raise HTTPException(404, '纸品不存在')
    from app.services.carton_supplier_portal import supplier_mark_asset_document
    asset = supplier_mark_asset_document(db, user, row.factory_id, payload.asset_id)
    if asset.revision != payload.asset_revision: raise HTTPException(409, '资料版本已变更')
    validate_asset_target(db, asset, row)
    if asset.size_bytes > 10 * 1024 * 1024: raise HTTPException(422, '制作资料不能超过 10 MiB')
    file = SpecialAttachment(id=special.uid('CSA-SP-'), factory_id=row.factory_id, request_id=row.id,
        line_id=line.id, role='DRAFT', filename=asset.file_name, media_type=asset.content_type,
        sha256=asset.sha256, size=asset.size_bytes, content=asset.content, created_by=user.id,
        created_at=special.core.now_text(), version=row.revision + 1)
    db.add(file)
    link_event(db, user, asset, row, line, file.id)
    special.version(db, user, row, 'ATTACHMENT_ADDED')
    return special.finish(db, user, payload, row, 'MARK_PROPOSE', digest, external=True)


def set_mark(db, user, identifier, line_id, payload):
    user = special.locked_actor(db, user, payload.factory_id)
    row = special.access(db, user, payload.factory_id, identifier)
    if not special.flags(db, user, row, False)["can_confirm_material"]:
        raise HTTPException(403, "只有本厂内部负责人可确认制作资料")
    digest, saved = special.replay(db, user, payload, "MARK_SET", identifier, line_id)
    if saved: return saved
    special.require_revision(row, payload)
    line = db.get(SpecialLine, line_id)
    if line is None or line.request_id != row.id or line.factory_id != row.factory_id:
        raise HTTPException(404, "未找到此订单纸品明细")
    file = None
    if payload.mark_mode == "EXISTING":
        require_library(user, row.factory_id)
        asset = db.get(CartonMarkAsset, payload.asset_id)
        if not asset or asset.factory_id != row.factory_id or asset.is_archived:
            raise HTTPException(404, "箱唛资料不存在或无权访问")
        if asset.revision != payload.asset_revision:
            raise HTTPException(409, "箱唛资料版本已变更，请重新选择并确认")
        validate_asset_target(db, asset, row)
        if asset.size_bytes > 10 * 1024 * 1024:
            raise HTTPException(422, "订单制作资料不能超过 10 MiB，请拆分文件后上传")
        from app.services import carton_mark_asset_workflow as lifecycle
        from app.schemas.carton_mark import CartonMarkAssetClassification
        if lifecycle.current(db, asset).status != 'READY':
            lifecycle.classify(db, user, row.factory_id, asset.id,
                CartonMarkAssetClassification(status='READY', revision=asset.revision, note='订单制作稿确认'), commit=False, material_confirmation=True)
        file = SpecialAttachment(id=special.uid("CSA-SP-"), factory_id=row.factory_id, request_id=row.id,
            line_id=line.id, role="CONFIRMED", filename=asset.file_name, media_type=asset.content_type,
            sha256=asset.sha256, size=asset.size_bytes, content=asset.content, created_by=user.id,
            created_at=special.core.now_text(), version=row.revision + 1)
        line.mark_asset_id = asset.id; line.mark_asset_revision = asset.revision
        link_event(db, user, asset, row, line, file.id, True)
    elif payload.mark_mode == "UPLOAD":
        draft = db.get(SpecialAttachment, payload.attachment_id)
        if not draft or draft.factory_id != row.factory_id or draft.request_id != row.id or draft.line_id != line.id:
            raise HTTPException(404, "制作稿必须属于本订单对应纸品明细")
        if draft.role not in {"DRAFT", "CONFIRMED"}:
            raise HTTPException(422, "参考资料不能直接作为制作稿，请先上传待确认稿")
        from pathlib import Path
        if Path(draft.filename).suffix.lower() not in {'.pdf', '.xls', '.xlsx', '.xlsm', '.jpg', '.jpeg', '.png', '.webp'}:
            raise HTTPException(422, '此文件仅作为参考附件；确认制作稿请上传 PDF、图片或 Excel')
        file = SpecialAttachment(id=special.uid("CSA-SP-"), factory_id=row.factory_id, request_id=row.id,
            line_id=line.id, role="CONFIRMED", filename=draft.filename, media_type=draft.media_type,
            sha256=draft.sha256, size=draft.size, content=draft.content, created_by=user.id,
            created_at=special.core.now_text(), version=row.revision + 1)
        from app.services import carton_mark_sharing as sharing, carton_mark_asset_workflow as lifecycle
        source_id = next((identifier for identifier, state in sharing.states(db, row.factory_id).items()
            if any(link['attachment_id'] == draft.id for link in state['special_orders'])), '')
        source = db.get(CartonMarkAsset, source_id) if source_id else None
        if source:
            if source.is_archived: raise HTTPException(409, '源资料已归档，请重新核实')
            validate_asset_target(db, source, row)
            from app.schemas.carton_mark import CartonMarkAssetClassification
            lifecycle.classify(db, user, row.factory_id, source.id,
                CartonMarkAssetClassification(status='READY', revision=source.revision, note='订单制作稿确认'), commit=False, material_confirmation=True)
            link_event(db, user, source, row, line, file.id, True)
        line.mark_asset_id = source.id if source else ''
        line.mark_asset_revision = source.revision if source else 0
    else:
        if payload.asset_id or payload.attachment_id:
            raise HTTPException(422, "无需箱唛或待补资料不能同时指定制作文件")
        line.mark_asset_id = ""; line.mark_asset_revision = 0
    if file: db.add(file)
    line.mark_attachment_id = file.id if file else ""
    line.mark_mode = payload.mark_mode
    special.version(db, user, row, "MATERIAL_CHANGED", execution=True)
    if row.status != "SUBMITTED": special.notify(db, row, "MATERIAL_CHANGED", audience="SUPPLIER")
    return special.finish(db, user, payload, row, "MARK_SET", digest)
