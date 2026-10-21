"""Reuse unified ITEM schedule recognition, without historical stock/shipments."""
from collections import Counter
from pathlib import PurePath
from pydantic import ValidationError
from app.schemas.indonesia_materials import Order
from app.services.customer_order_history import parse_workbook, key
from app.services.indonesia_material_calculations import require
from app.services.indonesia_materials import Ledger, Record, digest, view
from app.services.transaction_lock import lock_transaction
from sqlalchemy import select


def parse_schedule(content, customer, recipient, workbook=None):
    parsed, warnings = workbook if workbook is not None else parse_workbook(content)
    require(len(parsed) <= 2000, '单次最多预览 2000 条合同交付行，请按本次业务拆分', 422)
    rows = []
    for index, source in enumerate(parsed):
        original = source['data']
        fields = original.get('history_fields', [])
        batch_values = [f['value'] for f in fields if key(f['header']) in {'交付批次', '批次', 'deliverybatch', 'batch'}]
        batch = batch_values[0] if len(batch_values) == 1 else '1'
        row = dict(index=index, customer=customer, recipient=recipient,
                   contract_no=original.get('contract_no') or source['reference_no'], po_no=original.get('po_no', ''),
                   item_no=source['product_no'], batch=batch, quantity=source['quantity'], unit='PCS',
                   delivery_date=source['requested_ship_date'], source_sheet=source['sheet'], source_row=source['row'],
                   issues=list(source['issues']), blocked=source['blocked'])
        units = [f['value'] for f in fields if key(f['header']) in {'单位', 'unit'}]
        if units:
            row['unit'] = units[0]
        if source['section'] != 'unshipped':
            row['blocked'] = True
            row['issues'].append('已走货／取消分区不作为新启用物料需求导入')
        if len(batch_values) > 1:
            row['blocked'] = True
            row['issues'].append('交付批次字段重复，请核对原表')
        actual_customer = source.get('customer_name', '')
        if actual_customer and actual_customer != customer:
            row['blocked'] = True
            row['issues'].append(f'原表客名为 {actual_customer}，与所选客户不一致')
        try:
            Order.model_validate({k: v for k, v in row.items() if k in Order.model_fields})
        except ValidationError:
            row['blocked'] = True
            row['issues'].append('合同参考号、货号、数量或成品出货日期不完整，请核对原表')
        rows.append(row)
    identities = Counter(tuple(row[k] for k in ('contract_no', 'item_no', 'batch')) for row in rows if not row['blocked'])
    for row in rows:
        if identities[tuple(row[k] for k in ('contract_no', 'item_no', 'batch'))] > 1:
            row['blocked'] = True
            row['issues'].append('同合同同货号存在多行，请在原表提供稳定的交付批次；不能把日期当作批次身份')
    # These schedules are new module intake, never opening-balance migration.
    for row in rows:
        row['source_blocked'] = row['blocked']
        row['source_issues'] = list(row['issues'])
    return rows, ['仅所选有效合同进入送印尼物料；不会迁入历史库存或生成历史出货。', *warnings[1:]]


def reconcile_rows(ledger, rows):
    from copy import deepcopy
    from app.services.indonesia_material_calculations import number
    result = deepcopy(rows)
    existing = {r.business_key: r for r in ledger.rows('order')}
    for row in result:
        row['blocked'] = row.get('source_blocked', row['blocked'])
        row['issues'] = list(row.get('source_issues', row['issues']))
        row['changes'] = []
        identity = [row[k] for k in ('customer', 'recipient', 'contract_no', 'item_no', 'batch')]
        order = existing.get(digest(identity))
        row['match_status'] = 'new'
        if not order and not row['blocked']:
            from fastapi import HTTPException
            try:
                ledger.validate_catalog_order(row)
            except HTTPException as error:
                row['blocked'] = True
                row['issues'].append(str(error.detail))
        if not order or row['blocked']:
            continue
        row['existing_order_id'] = order.id
        for field in Order.model_fields:
            if field == 'reason':
                continue
            old, new = order.data[field], row.get(field, '')
            equal = number(old) == number(new) if field == 'quantity' else old == new
            if not equal:
                row['changes'].append(dict(field=field, old=old, new=new))
        row['match_status'] = 'changed' if row['changes'] else 'unchanged'
        if row['changes'] and not row.get('imported_order_id'):
            row['blocked'] = True
            row['issues'].append('已有合同出现改期、数量或订单资料变化，请在原合同记录核对更新；本批其他新增行可继续选入')
    return result


def preview(db, user, factory, customer, recipient, filename, content, workbook=None, refresh_user=None):
    require(filename.lower().endswith('.xlsx'), '请上传统一排期 .xlsx 文件', 422)
    rows, warnings = parse_schedule(content, customer, recipient, workbook)
    ledger = Ledger(db, factory)
    import hashlib
    key_value = [hashlib.sha256(content).hexdigest(), customer, recipient]
    try:
        from app.services.identity_policy import lock_mutation
        lock_mutation(db)
        lock_transaction(db, 'indonesia-materials', factory)
        if refresh_user:
            original_actor = user.id
            user = refresh_user()
            require(user.id == original_actor, '账号身份已变化，请重新上传核对', 401)
        from app.services.indonesia_materials import authorize
        authorize(user, factory, 'write')
        ledger.fixed_customer(customer)
        previous = db.scalar(select(Record).where(Record.factory_id == factory, Record.kind == 'import', Record.business_key == digest(key_value)))
        if previous:
            result = view(previous)
            result['data']['rows'] = reconcile_rows(ledger, result['data']['rows'])
            return dict(record=result)
        asset = ledger.asset(PurePath(filename).name, content, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        record = ledger.save('import', dict(status='preview', filename=asset.filename, asset_id=asset.id, customer=customer,
                                           recipient=recipient, rows=reconcile_rows(ledger, rows), issues=warnings, provided_by=user.id), key=key_value)
        db.commit()
        return dict(record=view(record))
    except Exception:
        db.rollback()
        raise
