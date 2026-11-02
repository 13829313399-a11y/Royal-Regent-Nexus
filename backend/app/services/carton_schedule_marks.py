"""Read-only contract hints for schedule rows, including demand before purchase creation."""
import json
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select, or_

from app.models.carton_procurement import CartonImportBatch
from app.services import carton_mark_assets as assets, carton_mark_sharing as sharing
from app.services.carton_schedule_tracking import effective_po


def schedule_sources(db, factory):
    batches = db.execute(select(CartonImportBatch.id, CartonImportBatch.parse_summary_json).where(
        CartonImportBatch.factory_id == factory, CartonImportBatch.import_type == 'WEEKLY_SCHEDULE',
        CartonImportBatch.status != 'REJECTED')).all()
    result = {}
    for identifier, content in batches:
        summary = json.loads(content or '{}')
        code = (summary.get('schedule_customer') or {}).get('customer_code', '')
        result[identifier] = [{**row, 'schedule_customer_code': row.get('schedule_customer_code') or code}
                              for row in summary.get('rows', []) if isinstance(row, dict)]
    return result


def known_schedule_contracts(db, factory, user):
    from app.services.auth import has_permission_in_scope
    if not any(has_permission_in_scope(user, 'carton_procurement:read', factory, dep)
               for dep in ('carton', 'pmc-warehouse')):
        return set()
    from app.services.carton_customer_assignment import ensure_customer_operation
    result = set()
    for rows in schedule_sources(db, factory).values():
        for row in rows:
            code = row.get('schedule_customer_code')
            if not code:
                continue
            try:
                ensure_customer_operation(db, user, factory, code)
            except HTTPException:
                continue
            if row.get('contract_no'):
                result.add(row['contract_no'])
    return result


def project(rows, sources, orders, files):
    """Explicit order bindings never widen into automatic contract bindings."""
    normalize = lambda value: assets.identity(str(value or ''))
    owners = defaultdict(set)
    for source in sources:
        owners[normalize(source.get('contract_no'))].add(normalize(source.get('schedule_customer_code')))
    for order in orders:
        owners[normalize(order.contract_no)].add(normalize(order.customer_code))
    order_index = {order.id: order for order in orders}
    automatic, explicit = defaultdict(list), []
    for file in files:
        # Upload alone is not confirmation; this hint counts only usable-classified originals.
        if file.workflow.status != 'READY':
            continue
        if file.recognition_source in {'manual_order', 'manual_orders'} or file.bound_order_id:
            explicit.append(file)
        elif file.contract_number:
            automatic[normalize(file.contract_number)].append(file)
    output, selected = [], {}
    for row in rows:
        contract, code = normalize(row.get('contract_no')), normalize(row.get('schedule_customer_code'))
        matched = []
        review = not contract or not code
        candidates = automatic.get(contract, [])
        if candidates:
            if code and owners[contract] == {code}:
                matched.extend(candidates)
            else:
                review = True
        for file in explicit:
            for link in file.orders:
                order = order_index.get(link.id)
                if order and normalize(order.customer_code) == code and normalize(order.contract_no) == contract \
                        and normalize(order.item_no) == normalize(row.get('item_no')) \
                        and (row.get('order_id') == order.id or effective_po(row) == effective_po({'customer_po': order.customer_po})):
                    matched.append(file)
                    break
        identifiers = list(dict.fromkeys(file.id for file in matched))
        selected.update({file.id: file for file in matched})
        output.append(dict(source_sheet=row.get('source_sheet') or '', source_row=row.get('source_row') or 0,
                           status='UPLOADED' if identifiers else 'REVIEW' if review else 'MISSING', asset_ids=identifiers))
    return output, [dict(id=file.id, file_name=file.file_name, usage_status=file.workflow.status)
                    for file in selected.values()]


def workspace(db, user, factory, batch_id):
    sources = schedule_sources(db, factory)
    if batch_id not in sources:
        raise HTTPException(404, '有效的本厂业务排期不存在')
    from app.services.carton_customer_assignment import ensure_customer_operation
    rows = sources[batch_id]
    permitted, restricted = [], []
    for row in rows:
        try:
            if row.get('schedule_customer_code'):
                ensure_customer_operation(db, user, factory, row['schedule_customer_code'])
            permitted.append(row)
        except HTTPException:
            restricted.append(dict(source_sheet=row.get('source_sheet') or '', source_row=row.get('source_row') or 0,
                                   status='RESTRICTED', asset_ids=[]))
    from app.services import carton_asset_access as ownership
    if ownership.enabled():
        return quick_workspace(db,user,factory,batch_id,permitted,restricted)
    files = sharing.filter_internal(db, user, assets.list_assets(db, factory))
    result, files = project(permitted, [row for rows in sources.values() for row in rows],
                            assets.available_orders(db, factory), files)
    from app.services.carton_materials import folders, folder_id, output, resolve_target, authorize
    from app.schemas.carton_materials import Target
    material_folders = folders(db, factory)
    indexed = {(row.get('source_sheet'), row.get('source_row')): row for row in permitted}
    for item in result:
        row = indexed.get((item['source_sheet'], item['source_row']))
        if not row or not row.get('schedule_customer_code'): continue
        try:
            target = resolve_target(db, factory, 'warehouse', Target(kind='SCHEDULE', id=batch_id,
                sheet=item['source_sheet'], row=item['source_row']))
            identifier = folder_id(factory, target)
            if identifier in material_folders: authorize(db, user, factory, 'warehouse', material_folders[identifier])
        except HTTPException: continue
        if identifier in material_folders:
            item.update(materials_folder_id=identifier, materials_status=output(material_folders[identifier], 'warehouse')['status_label'])
    return dict(factory_id=factory, batch_id=batch_id, rows=result + restricted, assets=files)


def quick_workspace(db,user,factory,batch_id,rows,restricted):
    """One old-library projection; never count order-materials originals."""
    from app.models.carton_mark import CartonMarkAsset
    from app.services import carton_asset_access as access,carton_asset_targets as targets,carton_mark_asset_workflow as lifecycle
    selected={};matches=defaultdict(dict)
    for asset in db.scalars(select(CartonMarkAsset).where(or_(CartonMarkAsset.factory_id==factory,CartonMarkAsset.owner_department=='supplier'),
            CartonMarkAsset.is_archived.is_(False),CartonMarkAsset.recognition_source!='materials_folder',
            CartonMarkAsset.asset_purpose=='MATERIAL',CartonMarkAsset.owner_department.is_not(None))):
        state=lifecycle.current(db,asset)
        if state.status not in {'DRAFT','PENDING','READY'} or not access.visible(db,user,asset,view_factory=factory):continue
        linked=targets.valid(db,asset,factory)
        for row in rows:
            row_key=(row.get('source_sheet',''),row.get('source_row',0))
            value=dict(customer_code=row.get('schedule_customer_code',''),contract_no=row.get('contract_no',''),
                item_no=row.get('item_no',''),customer_po=effective_po(row))
            if any((target['kind']=='SCHEDULE' and target['id']==batch_id and target['sheet']==row_key[0] and target['row']==row_key[1])
                    or (target['kind']=='REGULAR' and target['identity']==targets.identity(value)
                        and sum(targets.identity(dict(customer_code=r.get('schedule_customer_code',''),contract_no=r.get('contract_no',''),
                            item_no=r.get('item_no',''),customer_po=effective_po(r)))==target['identity'] for r in rows)==1) for target in linked):
                matches[row_key][asset.id]=state.status
                selected[asset.id]=dict(id=asset.id,file_name=asset.file_name,usage_status=state.status)
    result=[]
    for row in rows:
        values=matches[(row.get('source_sheet',''),row.get('source_row',0))]
        count=len(values);ready=sum(x=='READY' for x in values.values());pending=sum(x=='PENDING' for x in values.values())
        result.append(dict(source_sheet=row.get('source_sheet',''),source_row=row.get('source_row',0),
            status='UPLOADED' if count else 'MISSING',asset_ids=list(values),has_materials=bool(count),
            confirmed_count=ready,pending_count=pending,draft_count=count-ready-pending,
            status_label=('有资料 · 已确认' if ready==count else '有资料 · 部分已确认' if ready else '有资料 · 待确认' if pending else '有资料 · 待处理') if count else '暂无资料'))
    return dict(factory_id=factory,batch_id=batch_id,source_policy='ASSET_V1',rows=result+restricted,assets=list(selected.values()))
