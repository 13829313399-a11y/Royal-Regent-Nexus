"""Confirmed document codes are read references; only warehouse posting moves stock."""
import hashlib
import io
import json
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4, uuid5

from fastapi import HTTPException
from sqlalchemy import inspect, select
from app.core.time import business_now
from app.models.material_handover import HandoverIssuer, HandoverDocument, HandoverSource, HandoverEvent, HandoverSupplierBinding, HandoverLinkCommand
from app.schemas.material_handover import HandoverData
from app.schemas.warehouse_operations import WarehouseDocumentRequest
from app.services.auth import can
from app.services import warehouse_operations as inventory
from app.services.fabric_receiving import quantity
from app.services.fabric_procurement_parser import dump, digest

FACTORY = 'huakang-c'
REVISION = '20261012_0156'


def ensure_schema(db):
    inventory.ensure_schema(db)
    inspector = inspect(db.get_bind())
    names = set(inspector.get_table_names())
    missing = []
    for model in (HandoverIssuer, HandoverDocument, HandoverSource, HandoverEvent, HandoverSupplierBinding, HandoverLinkCommand):
        if model.__tablename__ not in names:
            missing.append(model.__tablename__)
        else:
            columns = {c['name'] for c in inspector.get_columns(model.__tablename__)}
            missing += [f'{model.__tablename__}.{c.name}' for c in model.__table__.columns if c.name not in columns]
    if not missing and db.get_bind().dialect.name == 'sqlite':
        from sqlalchemy import text
        triggers = set(db.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'")).scalars())
        missing += [f'{name}_no_{action}' for name in ('material_handover_sources', 'material_handover_events', 'material_handover_supplier_bindings', 'material_handover_link_commands') for action in ('update', 'delete') if f'{name}_no_{action}' not in triggers]
    if not missing and db.get_bind().dialect.name == 'postgresql':
        from sqlalchemy import text
        triggers = set(db.execute(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgenabled IN ('O','A')")).scalars())
        missing += [f'{name}_immutable' for name in ('material_handover_sources', 'material_handover_events', 'material_handover_supplier_bindings', 'material_handover_link_commands') if f'{name}_immutable' not in triggers]
    if missing:
        raise HTTPException(503, f'制单扫码模块需先备份并迁移至 {REVISION}：' + ', '.join(missing))


@dataclass(frozen=True)
class Access:
    key: str
    name: str
    issuer_id: str | None = None
    supplier_id: str = ''


def staff(actor, action='read'):
    if not can(actor, 'fabric_operations:read', FACTORY, 'pmc-warehouse'):
        raise HTTPException(403, '没有当前布料仓查询权限')
    permission = 'fabric_warehouse:import' if action == 'manage' else 'fabric_operations:operate'
    if action != 'read' and not can(actor, permission, FACTORY, 'pmc-warehouse'):
        raise HTTPException(403, '没有当前布料仓本项操作权限')
    return Access('user:' + actor.id, actor.display_name)


def external(db, token):
    ensure_schema(db)
    if not re.fullmatch(r'[A-Za-z0-9_-]{40,100}', token or ''):
        raise HTTPException(401, '制单链接无效，请联系仓库重新发放')
    issuer = db.scalar(select(HandoverIssuer).where(HandoverIssuer.factory_id == FACTORY,
        HandoverIssuer.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    if issuer is None or not issuer.active or issuer.expires_at <= business_now().isoformat():
        raise HTTPException(401, '制单链接已到期或停用，请联系仓库')
    from app.services import material_handover_suppliers as parties
    identity=parties.binding(db,issuer.id)
    name=issuer.name
    if identity:
        try:name=parties.supplier(db,identity.supplier_id).name
        except HTTPException as error:raise HTTPException(401,'供应商基础资料已停用，请联系仓库') from error
    return Access('issuer:' + issuer.id, name, issuer.id, identity.supplier_id if identity else '')


def issuer_out(issuer,db=None):
    result={key: getattr(issuer, key) for key in ('id', 'name', 'kind', 'active', 'revision', 'expires_at', 'created_at')}
    identity=db.get(HandoverSupplierBinding,issuer.id) if db is not None else None
    if identity:
        from app.services.material_handover_suppliers import supplier
        result['name']=supplier(db,identity.supplier_id,active=False).name
    return {**result,'supplier_id':identity.supplier_id if identity else '',
        'supplier_code':json.loads(identity.supplier_snapshot_json)['code'] if identity else ''}


def create_issuer(db, actor, payload):
    from app.services.material_handover_suppliers import create
    return create(db,actor,payload)


def revoke_issuer(db, actor, identifier, payload):
    from app.services.material_handover_suppliers import action
    return action(db,actor,identifier,payload,'REVOKE')


def issuer_scope(db,access):
    return list(db.scalars(select(HandoverSupplierBinding.issuer_id).where(HandoverSupplierBinding.factory_id==FACTORY,
        HandoverSupplierBinding.supplier_id==access.supplier_id))) if access.supplier_id else [access.issuer_id]


def supplier_identity(db,row,body):
    identity=db.get(HandoverSupplierBinding,row.issuer_id) if row.issuer_id else None
    return identity.supplier_id if identity else body.get('supplier_id','')


def validate_party(db,access,data,document_issuer_id=None):
    issuer_id = document_issuer_id or access.issuer_id
    if issuer_id:
        issuer = db.get(HandoverIssuer, issuer_id)
        binding = db.get(HandoverSupplierBinding, issuer_id)
        supplier_id = binding.supplier_id if binding else ''
        name = issuer.name
        if supplier_id:
            from app.services.material_handover_suppliers import supplier
            name = supplier(db, supplier_id).name
        if data.kind!=('DELIVERY' if issuer.kind=='SUPPLIER' else 'ISSUE') or data.counterparty!=name or data.supplier_id!=supplier_id:
            raise HTTPException(403,'专用链接不能变更制单方或收发用途')
    elif data.kind=='DELIVERY' and data.supplier_id:
        from app.services.material_handover_suppliers import supplier
        if data.counterparty!=supplier(db,data.supplier_id).name:raise HTTPException(422,'请核对所选供应商基础资料与单据名称')


def document(db, access, identifier, *, lock=False):
    query = select(HandoverDocument).where(HandoverDocument.factory_id == FACTORY, HandoverDocument.id == identifier)
    if access.issuer_id:
        query = query.where(HandoverDocument.issuer_id.in_(issuer_scope(db,access)))
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise HTTPException(404, '未找到当前范围的单据')
    return row


def progress(db, identifier, *, entries=None):
    if entries is None:
        _, entries = inventory.projection(db, 'fabric')
    amounts, movements = {}, []
    for entry in entries.values():
        data = entry['data']
        if data.get('handover_document_id') != identifier or entry['kind'] not in {'RECEIPT', 'ISSUE'}:
            continue
        movements.append({'operation_id': entry['id'], 'kind': entry['kind'], 'line_id': data['handover_line_id'],
            'quantity': data['quantity'], 'business_date': entry['business_date'], 'reversed': bool(entry.get('reversed')),
            'actor_name': entry['actor_name'], 'batch_id': data.get('batch_id', '')})
        if not entry.get('reversed'):
            key = data['handover_line_id']
            amounts[key] = amounts.get(key, inventory.decimal('0')) + inventory.decimal(data['quantity'])
    return amounts, movements


def code(row):
    return f'MH1:{row.id}:{row.code_version}' if row.status == 'CONFIRMED' else ''


def output(db, row, *, with_progress=True):
    body = HandoverData.model_validate_json(row.data_json).model_dump(mode='json')
    body['supplier_id']=supplier_identity(db,row,body)
    if row.status=='DRAFT' and body['supplier_id']:
        from app.services.material_handover_suppliers import supplier
        body['counterparty']=supplier(db,body['supplier_id'],active=False).name
    extraction = json.loads(row.extraction_json)
    amounts, movements = progress(db, row.id) if with_progress else ({}, [])
    remaining, total_lines, completed = {}, len(body['lines']), 0
    for line in body['lines']:
        target = inventory.decimal(line['quantity']) if line['quantity'] else inventory.decimal('0')
        actual = amounts.get(line['id'], inventory.decimal('0'))
        remaining[line['id']] = {'processed': inventory.text(actual), 'remaining': inventory.text(max(inventory.decimal('0'), target - actual))}
        completed += target > 0 and actual >= target
    processing = 'COMPLETE' if total_lines and completed == total_lines else 'PARTIAL' if any(amounts.values()) else 'PENDING'
    source = db.get(HandoverSource, row.id)
    return {'id': row.id, 'factory_id': FACTORY, 'issuer_id': row.issuer_id, 'status': row.status, 'revision': row.revision,
        'code_version': row.code_version, 'code': code(row), 'data': body, 'warnings': extraction.get('warnings', []),
        'evidence': extraction.get('evidence', {}), 'engine': extraction.get('engine', ''), 'raw_text': extraction.get('raw_text', ''),
        'file_name': source.file_name if source else '', 'source_sha256': source.sha256 if source else '',
        'confirmed_at': row.confirmed_at, 'created_at': row.created_at, 'progress': remaining, 'processing_status': processing,
        'movements': movements}


def request_signature(kind, identifier, payload):
    body=payload.model_dump(mode='json')
    for line in body.get('lines', []):
        for key in ('purchase_source_id', 'expected_source_revision', 'expected_receipt_count', 'difference_reason'):
            if line.get(key) in ('', None): line.pop(key, None)
    if body.get('data') is None:body.pop('data',None)
    if isinstance(body.get('data'),dict):
        data=body['data']
        if not data.get('supplier_id'):data.pop('supplier_id',None)
        for line in data.get('lines',[]):
            for key in ('unit_price','price_unit','currency','price_note'):
                if not line.get(key):line.pop(key,None)
    return digest([kind, identifier, body])


def replay(db, access, request_id, signature):
    previous = db.scalar(select(HandoverEvent).where(HandoverEvent.factory_id == FACTORY,
        HandoverEvent.actor_key == access.key, HandoverEvent.request_id == str(request_id)))
    if previous:
        if previous.request_hash != signature:
            raise HTTPException(409, '提交编号已用于其他内容，请先核对原单')
        return json.loads(previous.result_json)
    return None


def event(db, access, row, kind, request_id, signature, detail, result):
    db.add(HandoverEvent(id='MHE-' + uuid4().hex, document_id=row.id, factory_id=FACTORY, revision=row.revision,
        kind=kind, actor_key=access.key, actor_name=access.name, request_id=str(request_id), request_hash=signature,
        detail_json=dump(detail), result_json=dump(result), occurred_at=business_now().isoformat()))


def duplicate_upload(db, access, sha):
    return db.scalar(select(HandoverDocument).join(HandoverSource, HandoverSource.document_id == HandoverDocument.id)
        .where(HandoverDocument.factory_id == FACTORY, HandoverDocument.owner_key == access.key,
            HandoverDocument.status != 'VOID', HandoverSource.sha256 == sha))


def create_document(db, access, name, content, extraction, request_id):
    ensure_schema(db); inventory.procurement.lock_factory(db)
    signature = digest(['UPLOAD', name, hashlib.sha256(content).hexdigest()])
    previous = replay(db, access, request_id, signature)
    if previous is not None:
        return previous
    old = duplicate_upload(db, access, hashlib.sha256(content).hexdigest())
    if old:
        db.rollback(); return output(db, old)
    data = HandoverData.model_validate(extraction['data'])
    if access.issuer_id:
        issuer = db.get(HandoverIssuer, access.issuer_id)
        data.kind = 'DELIVERY' if issuer.kind == 'SUPPLIER' else 'ISSUE'
        data.counterparty = access.name
        data.supplier_id = access.supplier_id
    identifier = 'MHD-' + uuid4().hex
    now = business_now().isoformat()
    row = HandoverDocument(id=identifier, factory_id=FACTORY, issuer_id=access.issuer_id, owner_key=access.key,
        status='DRAFT', revision=1, code_version=0, data_json=data.model_dump_json(), extraction_json=dump(extraction),
        confirmed_by='', confirmed_at='', created_at=now, updated_at=now)
    db.add(row); db.flush()
    import mimetypes
    db.add(HandoverSource(document_id=identifier, factory_id=FACTORY, file_name=name,
        content_type=mimetypes.guess_type(name)[0] or 'application/octet-stream', sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content), content=content))
    db.flush()
    result = output(db, row, with_progress=False)
    event(db, access, row, 'UPLOAD', request_id, signature, {'sha256': hashlib.sha256(content).hexdigest()}, result)
    db.commit(); return result


def check_revision(row, expected):
    if row.revision != expected:
        raise HTTPException(409, '单据或收发进度已变化，请刷新后核对')


def save_document(db, access, identifier, payload):
    inventory.procurement.lock_factory(db)
    signature = request_signature('SAVE', identifier, payload)
    previous = replay(db, access, payload.request_id, signature)
    if previous is not None:
        return previous
    row = document(db, access, identifier, lock=True); check_revision(row, payload.expected_revision)
    if row.status != 'DRAFT':
        raise HTTPException(409, '已确认单据不可直接改写，请保留原版本并先作废未执行单据')
    data = payload.data
    if len({line.id for line in data.lines}) != len(data.lines):
        raise HTTPException(422, '明细行编号不能重复')
    validate_party(db,access,data,row.issuer_id)
    before = json.loads(row.data_json)
    row.data_json = data.model_dump_json(); row.revision += 1; row.updated_at = business_now().isoformat()
    db.flush(); result = output(db, row)
    event(db, access, row, 'SAVE', payload.request_id, signature, {'before': before, 'after': data.model_dump(mode='json')}, result)
    db.commit(); return result


def confirmation_issues(data):
    """Drafts may be incomplete; enumerate what a confirmed code still needs."""
    issues = []
    for value, label in ((data.source_no, '原单号'), (data.document_date, '单据日期'), (data.counterparty, '制单方')):
        if not value:
            issues.append('缺少' + label)
    if data.kind == 'DELIVERY' and not data.supplier_id:
        issues.append('供应商尚未关联，请仓库选择供应商基础资料')
    if not data.lines:
        issues.append('尚无物料明细，请添加明细或交仓库按原件补录')
    for index, line in enumerate(data.lines, 1):
        missing = ['缺少' + label for value, label in ((line.item_code, '物料编码'), (line.item_name, '物料名称'), (line.unit, '单位'), (line.material_category, '物料分类')) if not value]
        for value, label, allow_zero in ((line.quantity, '数量', False), (line.unit_price, '参考单价', True)):
            if allow_zero and not value:
                continue
            if not value:
                missing.append('缺少' + label)
                continue
            try:
                quantity(value, label, allow_zero=allow_zero)
            except HTTPException as error:
                missing.append(error.detail)
        if missing:
            issues.append(f'第 {index} 行' + (f'（{line.item_name}）' if line.item_name else '') + '：' + '；'.join(missing))
    return issues


def confirm(db, access, identifier, payload):
    inventory.procurement.lock_factory(db)
    signature = request_signature('CONFIRM', identifier, payload)
    previous = replay(db, access, payload.request_id, signature)
    if previous is not None:
        return previous
    row = document(db, access, identifier, lock=True); check_revision(row, payload.expected_revision)
    if row.status != 'DRAFT':
        raise HTTPException(409, '单据已确认或作废，请刷新')
    data = payload.data or HandoverData.model_validate_json(row.data_json)
    if not payload.data and access.issuer_id:data.supplier_id=access.supplier_id;data.counterparty=access.name
    validate_party(db,access,data,row.issuer_id)
    if len({line.id for line in data.lines})!=len(data.lines):raise HTTPException(422,'明细行编号不能重复')
    issues = confirmation_issues(data)
    if issues:
        raise HTTPException(422, '确认打印前请补全：' + '；'.join(issues) + '。也可先保存，交仓库补全。')
    if data.kind=='DELIVERY':
        from app.services.material_handover_suppliers import supplier
        supplier(db,data.supplier_id)
    if json.loads(row.extraction_json).get('warnings') and not payload.acknowledge_warnings:
        raise HTTPException(422, '请核对识别提示和原件，确认明细后再生成二维码')
    for line in data.lines:
        line.quantity = inventory.text(quantity(line.quantity, '单据数量'))
        if line.unit_price:line.unit_price=inventory.text(quantity(line.unit_price,'参考单价',allow_zero=True))
    for old in db.scalars(select(HandoverDocument).where(HandoverDocument.factory_id == FACTORY,
        HandoverDocument.status == 'CONFIRMED', HandoverDocument.id != identifier)):
        existing = json.loads(old.data_json)
        same_party=(supplier_identity(db,old,existing)==data.supplier_id) if data.kind=='DELIVERY' else existing['counterparty']==data.counterparty
        if same_party and all(existing[k] == getattr(data, k) for k in ('kind', 'source_no')):
            raise HTTPException(409, '同一制单方和原单号已确认，请使用原单二维码，勿重复建单')
    row.data_json = data.model_dump_json(); row.status = 'CONFIRMED'; row.revision += 1; row.code_version = 1
    row.confirmed_by = access.key; row.confirmed_at = row.updated_at = business_now().isoformat()
    db.flush(); result = output(db, row)
    event(db, access, row, 'CONFIRM', payload.request_id, signature, {'confirmed': data.model_dump(mode='json')}, result)
    db.commit(); return result


def void(db, access, identifier, payload):
    inventory.procurement.lock_factory(db)
    signature = request_signature('VOID', identifier, payload)
    previous = replay(db, access, payload.request_id, signature)
    if previous is not None:
        return previous
    row = document(db, access, identifier, lock=True); check_revision(row, payload.expected_revision)
    if not payload.reason:
        raise HTTPException(422, '请填写作废原因')
    if row.status == 'VOID' or progress(db, identifier)[1]:
        raise HTTPException(409, '单据已作废或已有库存流水；请先在库存更正流程核对原记录')
    row.status = 'VOID'; row.revision += 1; row.updated_at = business_now().isoformat()
    db.flush(); result = output(db, row)
    event(db, access, row, 'VOID', payload.request_id, signature, {'reason': payload.reason}, result)
    db.commit(); return result


def scan(db, access, value):
    match = re.fullmatch(r'MH1:(MHD-[0-9a-f]{32}):([1-9][0-9]{0,5})', value.strip())
    if not match:
        raise HTTPException(422, '请扫描本模块生成的单据码，或完整输入码下方的编号')
    row = document(db, access, match[1])
    if row.status != 'CONFIRMED' or row.code_version != int(match[2]):
        raise HTTPException(409, '二维码版本已失效或单据未确认 / 已作废，请使用有效原单')
    return output(db, row)


def post(db, actor, identifier, payload):
    access = staff(actor, 'operate'); ensure_schema(db)
    state = inventory.procurement.lock_factory(db)
    signature = request_signature('POST', identifier, payload)
    previous = replay(db, access, payload.request_id, signature)
    if previous is not None:
        return previous
    row = document(db, access, identifier, lock=True); check_revision(row, payload.expected_revision)
    if row.status != 'CONFIRMED' or row.code_version != payload.code_version:
        raise HTTPException(409, '单据二维码版本已失效')
    data = HandoverData.model_validate_json(row.data_json)
    if data.kind=='DELIVERY':
        from app.services.material_handover_suppliers import supplier
        supplier(db,supplier_identity(db,row,data.model_dump(mode='json')))
    if payload.business_date < data.document_date:
        raise HTTPException(422, '实际收发日期不能早于单据日期')
    remaining, _ = progress(db, identifier)
    source_lines = {line.id: line for line in data.lines}
    selected_totals = {}
    _, entries = inventory.projection(db, 'fabric')
    actual_revision = max((e['sequence'] for e in entries.values()), default=0)
    if actual_revision != payload.expected_inventory_revision:
        raise HTTPException(409, '库存已变化，请刷新后核对')
    selected_line_ids = {selection.line_id for selection in payload.lines}
    for entry in entries.values():
        if entry['kind'] != 'CORRECTION':
            continue
        original = entries.get(entry['data'].get('original_id'), {}).get('data', {})
        if original.get('handover_document_id') == identifier and original.get('handover_line_id') in selected_line_ids \
                and payload.business_date.isoformat() < entry['business_date']:
            raise HTTPException(409, '重新收发日期不能早于该明细的冲销日期，请核对实际日期')
    for selection in payload.lines:
        line = source_lines.get(selection.line_id)
        if line is None:
            raise HTTPException(422, '所选明细不属于本单')
        amount = quantity(selection.quantity, '本次数量')
        selected_totals[line.id] = selected_totals.get(line.id, inventory.decimal('0')) + amount
        if remaining.get(line.id, inventory.decimal('0')) + selected_totals[line.id] > inventory.decimal(line.quantity):
            raise HTTPException(409, '本次累计数量超过本单未完成数量')
    from app.services.material_handover_procurement import prepare_links
    purchase_links = prepare_links(db, actor, row, data, payload.lines)
    result_movements = []
    for index, selection in enumerate(payload.lines):
        line = source_lines[selection.line_id]
        if data.kind == 'ISSUE':
            stock, _ = inventory.projection(db, 'fabric')
            batch = inventory.batch_for(stock, selection.batch_id)
            if batch['item_code'] != line.item_code or batch['unit'] != line.unit:
                raise HTTPException(422, '实际批次物料和单位必须与所选明细一致，不能自动换算')
            if line.lot and batch.get('lot', '') != line.lot:
                raise HTTPException(422, '所选批次缸号与本单指定缸号不符')
        body = WarehouseDocumentRequest(factory_id=FACTORY, request_id=uuid5(payload.request_id, f'{identifier}:{index}'),
            expected_revision=actual_revision + index, kind='RECEIPT' if data.kind == 'DELIVERY' else 'ISSUE',
            business_date=payload.business_date, source_system='MATERIAL_HANDOVER', source_no=data.source_no,
            source_line=f'{identifier}:{line.id}:{digest([str(payload.request_id), index])[:24]}', source_version=str(row.code_version),
            item_code=line.item_code, item_name=line.item_name, unit=line.unit, material_category=line.material_category,
            quantity=selection.quantity, lot=selection.lot or line.lot, roll_no=selection.roll_no or line.roll_no,
            location_id=selection.location_id, batch_id=selection.batch_id, counterparty=data.counterparty,
            production_no=line.production_no or data.production_no, reason=data.note)
        result_movements.append(inventory.post(db, actor, 'fabric', body, _state=state, _commit=False,
            _metadata={'handover_document_id': identifier, 'handover_line_id': line.id, 'handover_code_version': row.code_version,
                'handover_line_snapshot': line.model_dump(mode='json'),
                'handover_supplier_id': supplier_identity(db,row,data.model_dump(mode='json')),
                'handover_contract_no': line.contract_no or data.contract_no, 'handover_product_no': line.product_no or data.product_no,
                'handover_request_id': str(payload.request_id), **purchase_links[index]}))
    row.revision += 1; row.updated_at = business_now().isoformat(); db.flush()
    result = output(db, row)
    event(db, access, row, 'POST', payload.request_id, signature, {'operation_ids': [m['id'] for m in result_movements],
        'selections': payload.model_dump(mode='json')}, result)
    db.commit(); return result


def qr_svg(row):
    if row.status != 'CONFIRMED':
        raise HTTPException(409, '仅已确认单据可打印二维码')
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics import renderSVG
    qr = QrCodeWidget(code(row), barLevel='M')
    x, y, right, top = qr.getBounds()
    drawing = Drawing(240, 240, transform=[240/(right-x), 0, 0, 240/(top-y), 0, 0])
    drawing.add(qr)
    return renderSVG.drawToString(drawing)
