"""Isolated material fulfilment ledger. No writes to finished-goods order state."""
import hashlib
import json
from copy import deepcopy
from datetime import date, timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError, OperationalError
from app.models.indonesia_materials import IndonesiaMaterialRecord as Record, IndonesiaMaterialCommand as Receipt, IndonesiaMaterialAsset as Asset
from app.models.indonesia_materials import IndonesiaMaterialCustomer as Customer
from app.schemas import indonesia_materials as s
from app.services.auth import authorization_decision
from app.core.time import business_now
from app.services.transaction_lock import lock_transaction
from app.services.identity_policy import lock_mutation
from app.services.indonesia_material_calculations import require, number, decimal_text, ZERO, production_plan, packaging_totals, precise_decimals

FACTORIES = {'huakang-a', 'huakang-b', 'huakang-c', 'huakang-d', 'huadeng', 'huaxing'}
TABLES = (Record.__table__, Receipt.__table__, Asset.__table__, Customer.__table__)
ACTIONS = ('read', 'write', 'receipt_confirm', 'export')


def now_text():
    return business_now().isoformat(timespec='seconds')


def allowed(user, factory, action):
    departments = ('sales-business', 'pmc-warehouse') if action in {'read', 'receipt_confirm'} else ('sales-business',)
    return any(authorization_decision(user, 'indonesia_material:' + action, factory, department)[0] for department in departments)


def authorize(user, factory, action='read'):
    require(factory in FACTORIES, '请选择明确的河源厂区', 422)
    require(allowed(user, factory, 'read') and allowed(user, factory, action), '没有该厂区送印尼物料的相应操作权限', 403)


def ready(db):
    inspector = inspect(db.connection())
    names = set(inspector.get_table_names())
    require(all(t.name in names and {c.name for c in t.columns} <= {c['name'] for c in inspector.get_columns(t.name)} for t in TABLES),
            '送印尼物料需要先完成显式数据库迁移 20261021_0169（固定客人资料）', 503)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def view(row):
    return dict(id=row.id, kind=row.kind, version=row.version, data=deepcopy(row.data), updated_at=row.updated_at)


class Ledger:
    def __init__(self, db, factory):
        self.db, self.factory, self.changes = db, factory, []
        self._rows = {}
        self._shipped = None

    def get(self, entity_id, kind):
        row = self.db.get(Customer if kind == 'customer' else Record, entity_id) if entity_id else None
        require(row is not None and row.factory_id == self.factory and row.kind == kind, '业务记录不存在或不属于当前厂区', 404)
        return row

    def rows(self, kind):
        if kind not in self._rows:
            model = Customer if kind == 'customer' else Record
            query = select(model).where(model.factory_id == self.factory)
            if model is Record:
                query = query.where(Record.kind == kind)
            self._rows[kind] = list(self.db.scalars(query.order_by(model.id)))
        return self._rows[kind]

    def save(self, kind, data, row=None, key=None):
        before = view(row) if row else None
        if row is None:
            values = dict(id=str(uuid4()), factory_id=self.factory, business_key=digest(key or str(uuid4())), version=0)
            row = Customer(**values) if kind == 'customer' else Record(kind=kind, **values)
            self.db.add(row)
        elif key is not None:
            row.business_key = digest(key)
        row.data = deepcopy(data)
        row.version += 1
        row.updated_at = now_text()
        self.db.flush()
        self._rows.pop(kind, None)
        if kind == 'shipment':
            self._shipped = None
        self.changes.append(dict(before=before, after=view(row)))
        return row

    def matching_product(self, order):
        return next((r for r in self.rows('product') if r.data['code'] == order['item_no'] and r.data['customer'] == order['customer']), None)

    def fixed_customer(self, name):
        customer = next((r for r in self.rows('customer') if r.data['name'] == name), None)
        require(customer is not None, '请先在当前厂区基础资料库新增该固定客人', 422)
        require(customer.data['status'] == 'active', '该固定客人已停用，请先核对基础资料', 422)
        return customer

    def validate_catalog_order(self, data):
        customer = self.fixed_customer(data['customer'])
        product = self.matching_product(data)
        require(product is not None, '该货号未配置在当前厂区此固定客人名下，请先维护客人货号', 422)
        require(bool(product.data['materials']), '该货号尚未配置物料及单件用量，请先补齐基础资料', 422)
        return customer, product

    def snapshot_order(self, data, prior=None, *, require_catalog=False):
        customer = self.validate_catalog_order(data)[0] if require_catalog else None
        product = self.matching_product(data)
        data = deepcopy(data)
        if customer:
            data['customer_snapshot'] = view(customer)
        elif prior and prior.get('customer_snapshot'):
            data['customer_snapshot'] = deepcopy(prior['customer_snapshot'])
        require(not product or product.data['unit'] == data['unit'], '合同数量单位必须与日产能单位一致', 422)
        old_demands = {d['material_id']: d for d in (prior or {}).get('demands', [])}
        data['product_snapshot'] = view(product) if product else None
        data['plan'] = production_plan(data['quantity'], product.data['daily_capacity'], data['delivery_date'], product.data['transport_days']) if product else None
        data['demands'] = []
        for recipe in (product.data['materials'] if product else []):
            material = self.get(recipe['material_id'], 'material')
            computed = decimal_text(number(data['quantity']) * number(recipe['usage']))
            previous = old_demands.get(material.id, {})
            demand = dict(id=previous.get('id', str(uuid4())), material_id=material.id,
                          code=material.data['code'], name=material.data['name'], unit=material.data['unit'],
                          computed_quantity=computed, quantity=previous.get('quantity') if previous.get('override_reason') else computed,
                          override_reason=previous.get('override_reason', ''), material_snapshot=view(material),
                          procurement_days=material.data['procurement_days'], purchase_start=None)
            if data['plan'] and demand['procurement_days'] is not None:
                demand['purchase_start'] = (date.fromisoformat(data['plan']['required_date']) - timedelta(days=demand['procurement_days'])).isoformat()
            data['demands'].append(demand)
        return data

    def demand(self, order_id, demand_id):
        order = self.get(order_id, 'order')
        demand = next((d for d in order.data['demands'] if d['id'] == demand_id), None)
        require(demand is not None, '合同物料需求不存在', 404)
        return order, demand

    def shipped(self, allocation_id):
        if self._shipped is None:
            self._shipped = {}
            for row in self.rows('shipment'):
                if row.data['status'] != 'confirmed':
                    continue
                for line in row.data['lines']:
                    counts = self._shipped.setdefault(line['allocation_id'], [ZERO, ZERO])
                    counts[0] += number(line['normal_quantity'])
                    counts[1] += number(line['spare_quantity'])
        return self._shipped.get(allocation_id, [ZERO, ZERO])

    def validate_allocation(self, data, existing=None):
        supply = self.get(data['supply_id'], 'supply')
        _, demand = self.demand(data['order_id'], data['demand_id'])
        require(supply.data['material_id'] == demand['material_id'], '只能分配对应编码的同种物料', 422)
        require(supply.data['material_snapshot']['data']['unit'] == demand['unit'], '供应与合同物料单位不一致，需先核对', 422)
        require(supply.data['material_snapshot']['data']['specification'] == demand['material_snapshot']['data']['specification'],
                '供应与合同需求的物料规格不一致，不能混配', 422)
        require(number(data['normal_quantity']) + number(data['spare_quantity']) > 0, '分配数量必须大于零', 422)
        allocations = [r for r in self.rows('allocation') if not existing or r.id != existing.id]
        for field in ('normal_quantity', 'spare_quantity'):
            used = sum((number(r.data[field]) for r in allocations if r.data['supply_id'] == supply.id), ZERO)
            require(used + number(data[field]) <= number(supply.data[field]), '分配超过该批物料的正常量或备品余量')
        already = sum((number(r.data['normal_quantity']) + number(r.data['spare_quantity']) for r in allocations
                       if r.data['order_id'] == data['order_id'] and r.data['demand_id'] == data['demand_id']), ZERO)
        require(already + number(data['normal_quantity']) + number(data['spare_quantity']) <= number(demand['quantity']), '分配超过合同最终需求，请先调整需求')

    def validate_order_coverage(self, row, new_data):
        demands = {d['id']: d for d in new_data['demands']}
        totals = {}
        for allocation in self.rows('allocation'):
            if allocation.data['order_id'] != row.id:
                continue
            key = allocation.data['demand_id']
            count = number(allocation.data['normal_quantity']) + number(allocation.data['spare_quantity'])
            if not count:
                continue
            require(key in demands, '该物料已有分配，不能通过重算移除；请先处理分配')
            supply = self.get(allocation.data['supply_id'], 'supply')
            require(supply.data['material_snapshot']['data']['unit'] == demands[key]['unit'], '已分配物料的单位不能被重算改变')
            require(supply.data['material_snapshot']['data']['specification'] == demands[key]['material_snapshot']['data']['specification'],
                    '已分配物料规格与新需求不一致，请先处理原分配')
            totals[key] = totals.get(key, ZERO) + count
        for key, value in totals.items():
            require(value <= number(demands[key]['quantity']), '调整后需求低于已分配数量，请先处理分配')

    def execute(self, body, actor):
        action = body.action
        row = None
        kind = {'customer_save': 'customer', 'material_save': 'material', 'product_save': 'product', 'order_save': 'order', 'order_recalculate': 'order',
                'demand_adjust': 'order', 'supply_save': 'supply', 'supply_reply': 'supply', 'output_material_refresh': 'supply', 'receipt_confirm': 'supply',
                'reallocate': 'allocation', 'shipment_save': 'shipment', 'shipment_confirm': 'shipment', 'import_confirm': 'import'}.get(action)
        if body.entity_id:
            require(kind is not None, '此操作不接受现有记录编号', 422)
            row = self.get(body.entity_id, kind)
            require(row.version == body.expected_version, '记录已被更新，请刷新核对后重试')
        else:
            require(action in {'customer_save', 'material_save', 'product_save', 'order_save', 'supply_save', 'allocate', 'shipment_save'} and body.expected_version == 0,
                    '请选择原记录及其版本', 422)
        if action == 'customer_save':
            data = s.Customer.model_validate(body.data).model_dump(mode='json')
            require(not row or data['name'] == row.data['name'], '固定客人名称是关联身份，不能覆盖修改；请停用原客人后新增', 422)
            return self.save('customer', data, row, data['name'])
        if action == 'material_save':
            data = s.Material.model_validate(body.data).model_dump(mode='json')
            require(not row or data['code'] == row.data['code'], '物料编码不可覆盖修改；请维护原编码资料', 422)
            if row and any(data[k] != row.data[k] for k in ('unit', 'specification')):
                used = any(r.data['material_id'] == row.id for r in self.rows('supply')) or any(
                    d['material_id'] == row.id for r in self.rows('order') for d in r.data['demands'])
                require(not used, '该物料已被合同或供应引用，规格和计数单位不能覆盖修改；新规格请建立独立编码', 422)
            if data['image_data']:
                from app.services.indonesia_material_excel import validate_image
                validate_image(data['image_data'])
            return self.save('material', data, row, data['code'])
        if action == 'product_save':
            data = s.Product.model_validate(body.data).model_dump(mode='json')
            require(not row or (data['code'], data['customer']) == (row.data['code'], row.data['customer']), '货号与客户身份不可覆盖修改', 422)
            customer = self.fixed_customer(data['customer'])
            require(data['customer_id'] in {None, customer.id}, '客人与当前厂区固定客人编号不一致', 422)
            data['customer_id'] = customer.id
            ids = [r['material_id'] for r in data['materials']]
            require(len(ids) == len(set(ids)), '同货号不能重复定义同种物料用量', 422)
            for entity_id in ids:
                self.get(entity_id, 'material')
            return self.save('product', data, row, [data['customer'], data['code']])
        if action in {'order_save', 'order_recalculate'}:
            if action == 'order_recalculate':
                reason = s.Reason.model_validate(body.data).reason
                data = deepcopy(row.data)
                data['reason'] = reason
            else:
                data = s.Order.model_validate(body.data).model_dump(mode='json')
                if row:
                    require(data['reason'], '修改合同需填写原因', 422)
                    for key in ('customer', 'recipient', 'contract_no', 'item_no', 'batch'):
                        require(data[key] == row.data[key], '已建合同的身份字段不可修改，请核对原记录', 422)
                    data['source'] = row.data.get('source')
            data = self.snapshot_order(data, row.data if row else None, require_catalog=not row or action == 'order_recalculate')
            if row:
                self.validate_order_coverage(row, data)
            key = [data[k] for k in ('customer', 'recipient', 'contract_no', 'item_no', 'batch')]
            return self.save('order', data, row, key)
        if action == 'demand_adjust':
            change = s.Adjust.model_validate(body.data)
            data = deepcopy(row.data)
            demand = next((d for d in data['demands'] if d['id'] == change.demand_id), None)
            require(demand is not None, '需求不存在', 404)
            demand.update(quantity=decimal_text(change.quantity), override_reason=change.reason)
            self.validate_order_coverage(row, data)
            return self.save('order', data, row)
        if action == 'supply_save':
            data = s.Supply.model_validate(body.data).model_dump(mode='json')
            require(not row or (row.data['status'] == 'expected' and not any(a.data['supply_id'] == row.id for a in self.rows('allocation'))),
                    '已确认或已分配的供应不能覆盖修改；供应商回复请使用更新交期')
            material = self.get(data['material_id'], 'material')
            data.update(status='expected', material_snapshot=view(material), actual_date=None)
            siblings = [r for r in self.rows('supply') if r.id != (row.id if row else None) and
                        all(r.data[k] == data[k] for k in ('supplier', 'purchase_no', 'purchase_line'))]
            require(all(r.data['material_id'] == data['material_id'] and number(r.data['purchase_quantity']) == number(data['purchase_quantity']) for r in siblings),
                    '同采购单行的物料和采购总量必须一致', 422)
            total = number(data['normal_quantity']) + number(data['spare_quantity'])
            require(total > 0, '供应数量必须大于零', 422)
            require(total + sum((number(r.data['normal_quantity']) + number(r.data['spare_quantity']) for r in siblings), ZERO) <= number(data['purchase_quantity']),
                    '同采购单行累计正常量和备品量超过采购数量')
            return self.save('supply', data, row, [data[k] for k in ('supplier', 'purchase_no', 'purchase_line', 'batch')])
        if action == 'supply_reply':
            data = deepcopy(row.data)
            data.update(s.Reply.model_validate(body.data).model_dump(mode='json'))
            data['reply_updated_at'] = now_text()
            return self.save('supply', data, row)
        if action == 'output_material_refresh':
            reason = s.Reason.model_validate(body.data).reason
            material = self.get(row.data['material_id'], 'material')
            original = row.data['material_snapshot']['data']
            require(all(material.data[k] == original[k] for k in ('code', 'unit', 'specification')),
                    '出货资料与该批物料身份、规格或单位不一致，不能刷新替换实物', 422)
            data = deepcopy(row.data)
            data.update(output_material_snapshot=view(material), output_refresh_reason=reason, output_refreshed_by=actor)
            measured = data.setdefault('measured_weights', {})
            origins = data.setdefault('measured_weight_sources', {})
            for field in ('net_weight_kg', 'billing_weight_kg'):
                missing = original.get(field) is None or number(original[field]) == 0
                current = material.data.get(field)
                if missing and field not in measured and current is not None and number(current) > 0:
                    measured[field] = current
                    origins[field] = dict(material_id=material.id, version=material.version, actor_id=actor, measured_at=now_text())
            return self.save('supply', data, row)
        if action == 'receipt_confirm':
            require(row.data['status'] == 'expected', '该批物料已经确认入库')
            data = deepcopy(row.data)
            data.update(s.Receipt.model_validate(body.data).model_dump(mode='json'))
            data.update(status='received', confirmed_by=actor, confirmed_at=now_text())
            return self.save('supply', data, row)
        if action == 'allocate':
            data = s.Allocation.model_validate(body.data).model_dump(mode='json')
            self.validate_allocation(data)
            return self.save('allocation', data)
        if action == 'reallocate':
            change = s.Reallocation.model_validate(body.data).model_dump(mode='json')
            shipped = self.shipped(row.id)
            data = deepcopy(row.data)
            require((change['order_id'], change['demand_id']) != (data['order_id'], data['demand_id']), '请选择不同的目标需求', 422)
            for index, field in enumerate(('normal_quantity', 'spare_quantity')):
                require(number(change[field]) <= number(data[field]) - shipped[index], '只能调整尚未发出的已分配物料')
                data[field] = decimal_text(number(data[field]) - number(change[field]))
            self.save('allocation', data, row)
            target = dict(supply_id=data['supply_id'], **change)
            self.validate_allocation(target)
            return self.save('allocation', target)
        if action == 'shipment_save':
            require(not row or row.data['status'] == 'draft', '已确认出货不能覆盖修改')
            data = s.Shipment.model_validate(body.data).model_dump(mode='json')
            self.shipment_lines(data)
            data['status'] = 'draft'
            return self.save('shipment', data, row)
        if action == 'shipment_confirm':
            require(not body.data, '确认出货不接受覆盖数据', 422)
            require(row.data['status'] == 'draft', '该出货已确认')
            data = deepcopy(row.data)
            lines = self.shipment_lines(data, for_confirm=True)
            packed = packaging_totals(data['packages'], lines)
            data.update(status='confirmed', confirmed_by=actor, confirmed_at=now_text(),
                        snapshot_lines=list(lines.values()), packing_totals=packed)
            # Validate and freeze bytes before posting; a rejected output never ships stock.
            from app.services.indonesia_material_excel import export_shipment_with_summary
            content, supplier_summary = export_shipment_with_summary(data)
            asset = self.asset(f"{data['shipment_date']}_{data['customer']}_{data['recipient']}_出货明细.xlsx", content,
                               'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            data['export_asset_id'] = asset.id
            data['export_layout_version'] = 'material_row_v2'
            data['export_material_count'] = len({line['material']['code'] for line in lines.values()})
            data['supplier_summary'] = supplier_summary
            return self.save('shipment', data, row)
        if action == 'import_confirm':
            from app.services.indonesia_material_import import reconcile_rows
            selection = s.ImportSelection.model_validate(body.data)
            require(len(selection.indexes) == len(set(selection.indexes)), '不可重复选择同一行', 422)
            imported = list(row.data.get('order_ids', []))
            sources = reconcile_rows(self, row.data['rows'])
            for index in selection.indexes:
                source = next((r for r in sources if r['index'] == index), None)
                require(source is not None and not source.get('blocked'), '所选行存在资料问题，请先核对原表', 422)
                require(not source.get('imported_order_id'), '所选行已在本导入中确认，请选择未导入行', 422)
                order = s.Order.model_validate({k: v for k, v in source.items() if k in s.Order.model_fields}).model_dump(mode='json')
                key = [order[k] for k in ('customer', 'recipient', 'contract_no', 'item_no', 'batch')]
                existing = self.db.scalar(select(Record).where(Record.factory_id == self.factory, Record.kind == 'order', Record.business_key == digest(key)))
                if existing:
                    require(source['match_status'] == 'unchanged',
                            '排期包含已有合同的变更，请在合同原记录中核对修改，不可重新建单')
                    source['imported_order_id'] = existing.id
                    if existing.id not in imported:
                        imported.append(existing.id)
                    continue
                order['source'] = dict(import_id=row.id, asset_id=row.data['asset_id'], sheet=source['source_sheet'], row=source['source_row'], order_center_id=None)
                new_order = self.save('order', self.snapshot_order(order, require_catalog=True), key=key)
                imported.append(new_order.id)
                source['imported_order_id'] = new_order.id
            data = deepcopy(row.data)
            selected_indexes = list(dict.fromkeys([*data.get('selected_indexes', []), *selection.indexes]))
            remaining = [r for r in sources if not r['blocked'] and not r.get('imported_order_id')]
            data.update(status='partial' if remaining else 'confirmed', order_ids=imported, selected_indexes=selected_indexes, rows=sources)
            return self.save('import', data, row)
        raise HTTPException(422, '不支持的操作')

    @precise_decimals
    def shipment_lines(self, data, for_confirm=False):
        lines = {}
        for line in data['lines']:
            key = line['allocation_id']
            require(key not in lines, '同次出货不能重复选择分配行', 422)
            allocation = self.get(key, 'allocation')
            supply = self.get(allocation.data['supply_id'], 'supply')
            order, demand = self.demand(allocation.data['order_id'], allocation.data['demand_id'])
            require(order.data['customer'] == data['customer'] and order.data['recipient'] == data['recipient'], '本次出货只能包含同一客户、同一接收方', 422)
            require(supply.data['status'] == 'received', '船务确认入库后才能出货')
            require(number(line['normal_quantity']) + number(line['spare_quantity']) > 0, '本次出货数量必须大于零', 422)
            shipped = self.shipped(key)
            for index, field in enumerate(('normal_quantity', 'spare_quantity')):
                require(number(line[field]) <= number(allocation.data[field]) - shipped[index], '本次数量超过该分配行未发的正常量或备品量')
            material = deepcopy(supply.data['material_snapshot']['data'])
            refreshed = supply.data.get('output_material_snapshot')
            if refreshed:
                for field in ('name', 'english_name', 'specification', 'category', 'usage', 'department', 'export_company', 'image_data'):
                    material[field] = refreshed['data'][field]
                # Explicitly fill missing measured facts; never overwrite known values.
                for field in ('net_weight_kg', 'billing_weight_kg'):
                    if material.get(field) is None or number(material[field]) == 0:
                        material[field] = supply.data.get('measured_weights', {}).get(field)
            basis = number(line['normal_quantity'])
            amount = None
            weight_missing = supply.data['billing_basis'] == 'weight' and basis > 0 and (
                material.get('billing_weight_kg') is None or number(material['billing_weight_kg']) <= 0)
            require(not for_confirm or not weight_missing, '按重量计费需明确有效单件计费重量（与净重分开维护）', 422)
            if not weight_missing:
                if supply.data['billing_basis'] == 'weight' and basis > 0:
                    basis *= number(material['billing_weight_kg'])
                amount = decimal_text(basis / number(supply.data['billing_factor']) * number(supply.data['price']))
            lines[key] = dict(**line, material=deepcopy(material), supply=deepcopy(supply.data),
                              contract_no=order.data['contract_no'], item_no=order.data['item_no'],
                              order_id=order.id, demand_id=demand['id'], amount=amount)
        return lines

    def asset(self, filename, content, media_type):
        asset = Asset(id=str(uuid4()), factory_id=self.factory, filename=filename[:240], content=content,
                      media_type=media_type, sha256=hashlib.sha256(content).hexdigest(), created_at=now_text())
        self.db.add(asset)
        self.db.flush()
        return asset


def run_command(db, user, body, *, refresh_user):
    action = 'receipt_confirm' if body.action == 'receipt_confirm' else 'write'
    authorize(user, body.factory_id, action)
    ready(db)
    fingerprint = digest(body.model_dump(mode='json'))
    try:
        # Serialize with IAM revocation before acquiring the business resource.
        lock_mutation(db)
        lock_transaction(db, 'indonesia-materials', body.factory_id)
        current_user = refresh_user()
        require(current_user.id == user.id, '账号身份已变化，请重新核对操作', 401)
        user = current_user
        authorize(user, body.factory_id, action)
        previous = db.get(Receipt, body.operation_id)
        if previous:
            require(previous.actor_id == user.id and previous.factory_id == body.factory_id and previous.fingerprint == fingerprint,
                    '操作编号已用于不同请求，请核对原操作结果')
            return previous.result
        ledger = Ledger(db, body.factory_id)
        result = dict(record=view(ledger.execute(body, user.id)))
        db.add(Receipt(operation_id=body.operation_id, factory_id=body.factory_id, actor_id=user.id,
                       action=body.action, fingerprint=fingerprint, changes=ledger.changes, result=result, created_at=now_text()))
        db.commit()
        return result
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise HTTPException(409, '记录重复或同时被修改，请刷新后核对；不会部分保存') from exc
    except Exception:
        db.rollback()
        raise


def workspace(db, user, factory):
    authorize(user, factory)
    ready(db)
    ledger = Ledger(db, factory)
    rows = list(db.scalars(select(Record).where(Record.factory_id == factory).order_by(Record.updated_at.desc()).limit(5001)))
    rows += list(db.scalars(select(Customer).where(Customer.factory_id == factory).order_by(Customer.updated_at.desc()).limit(5001)))
    require(len(rows) <= 5000, '当前厂区记录超过首期工作区容量，请先联系管理员扩展分页', 409)
    for kind in ('customer', 'material', 'product', 'order', 'supply', 'allocation', 'shipment', 'import'):
        ledger._rows[kind] = [row for row in rows if row.kind == kind]
    supplies = {r.id: r for r in rows if r.kind == 'supply'}
    allocations = [r for r in rows if r.kind == 'allocation']
    board = []
    for order in (r for r in rows if r.kind == 'order'):
        data = deepcopy(order.data)
        for demand in data['demands']:
            assigned = [a for a in allocations if a.data['order_id'] == order.id and a.data['demand_id'] == demand['id']
                        and number(a.data['normal_quantity']) + number(a.data['spare_quantity']) > 0]
            total = sum((number(a.data['normal_quantity']) + number(a.data['spare_quantity']) for a in assigned), ZERO)
            coverage = sum((number(a.data['normal_quantity']) + number(a.data['spare_quantity']) for a in assigned if supplies[a.data['supply_id']].data['status'] == 'received'), ZERO)
            supplied = [supplies[a.data['supply_id']].data for a in assigned]
            promised = [s.get('promised_date') for s in supplied]
            promised_date = max((d for d in promised if d), default=None)
            actual_date = max((s.get('actual_date') for s in supplied if s.get('actual_date')), default=None)
            required = (data.get('plan') or {}).get('required_date')
            awaiting = total < number(demand['quantity']) or any(not s.get('promised_date') for s in supplied if s['status'] != 'received')
            if coverage >= number(demand['quantity']):
                risk = 'late_received' if required and actual_date and actual_date > required else 'received'
            elif required and any(s.get('promised_date') and s['promised_date'] > required for s in supplied if s['status'] != 'received'):
                risk = 'late'
            elif awaiting:
                risk = 'awaiting_reply'
            else:
                risk = 'on_time'
            demand.update(allocated=decimal_text(total), coverage=decimal_text(coverage), shortage=decimal_text(max(number(demand['quantity'])-coverage, ZERO)),
                          shipped=decimal_text(sum((sum(ledger.shipped(a.id)) for a in assigned), ZERO)), promised_date=promised_date,
                          actual_date=actual_date, risk=risk)
        data['id'] = order.id
        data['planning_status'] = 'ready' if data['plan'] and all(d['procurement_days'] is not None for d in data['demands']) else 'missing_parameters'
        data['status'] = ('missing_master' if not data['demands'] else 'complete' if all(number(d['shortage']) == 0 for d in data['demands']) else 'missing_parameters' if data['planning_status'] != 'ready' else 'shortage')
        board.append(data)
    result = [view(r) for r in rows]
    for row in result:
        if row['kind'] == 'import' and row['data']['status'] != 'confirmed':
            from app.services.indonesia_material_import import reconcile_rows
            row['data']['rows'] = reconcile_rows(ledger, row['data']['rows'])
        if row['kind'] == 'allocation':
            normal, spare = ledger.shipped(row['id'])
            row['data'].update(shipped_normal=decimal_text(normal), shipped_spare=decimal_text(spare))
    return dict(records=result, board=board, permissions=[a for a in ACTIONS if allowed(user, factory, a)])
