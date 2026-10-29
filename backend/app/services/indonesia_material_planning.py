"""Update one contract's plan and explicitly append newly configured materials."""
from copy import deepcopy
from datetime import date, timedelta
from uuid import uuid4

from app.schemas.indonesia_materials import OrderPlan
from app.services.indonesia_material_calculations import require, production_plan, number, decimal_text, precise_decimals


def missing_recipe_materials(order, product):
    existing = {d['material_id'] for d in order.data['demands']}
    return [recipe for recipe in product.data['materials'] if recipe['material_id'] not in existing] if product else []


@precise_decimals
def save_order_plan(ledger, order, payload):
    change = OrderPlan.model_validate(payload).model_dump(mode='json')
    product = ledger.get(change['product_id'], 'product')
    require(product.version == change['product_version'], '货号资料已被更新，请重新核对计划参数')
    require((product.data['customer'], product.data['code'], product.data['unit']) ==
            (order.data['customer'], order.data['item_no'], order.data['unit']), '计划货号与本合同不一致', 422)
    demands = order.data['demands']
    additions = missing_recipe_materials(order, product) if change['sync_materials'] else []
    expected_ids = {d['material_id'] for d in demands} | {r['material_id'] for r in additions}
    require(bool(expected_ids), '本合同尚无物料需求，请先维护货号用量并生成合同需求', 422)
    ids = [item['material_id'] for item in change['materials']]
    require(len(ids) == len(set(ids)) and set(ids) == expected_ids,
            '采购周期必须完整对应本合同及货号新增物料，请重新载入最新资料', 422)
    materials = []
    for item in change['materials']:
        material = ledger.get(item['material_id'], 'material')
        require(material.version == item['expected_version'], '物料资料已被更新，请重新核对采购周期')
        require(change['sync_materials'] or item['procurement_days'] is not None, '请填写采购周期', 422)
        materials.append((material, item['procurement_days']))
    # Validate the calculation before any master write. All writes also share the command transaction.
    try:
        plan = production_plan(order.data['quantity'], change['daily_capacity'], order.data['delivery_date'], change['transport_days'])
        purchase_dates = {material.id: (date.fromisoformat(plan['required_date']) - timedelta(days=days)).isoformat() if days is not None else None
                          for material, days in materials}
    except (OverflowError, ValueError):
        require(False, '计划日期超出有效范围，请核对日产能、交货日期和周期', 422)
    product_data = deepcopy(product.data)
    product_data.update(daily_capacity=change['daily_capacity'], transport_days=change['transport_days'])
    if product_data != product.data:
        ledger.save('product', product_data, product)
    by_id = {}
    for material, days in materials:
        if material.data.get('procurement_days') != days:
            material_data = deepcopy(material.data)
            material_data['procurement_days'] = days
            ledger.save('material', material_data, material)
        by_id[material.id] = dict(version=material.version, procurement_days=days)
    data = deepcopy(order.data)
    from app.services.indonesia_materials import view
    for recipe in additions:
        material = ledger.get(recipe['material_id'], 'material')
        computed = decimal_text(number(data['quantity']) * number(recipe['usage']))
        data['demands'].append(dict(id=str(uuid4()), material_id=material.id,
            code=material.data['code'], name=material.data['name'], unit=material.data['unit'],
            computed_quantity=computed, quantity=computed, override_reason='', material_snapshot=view(material),
            recipe_snapshot=dict(product_id=product.id, product_version=product.version, usage=recipe['usage'])))
    data['plan'] = plan
    data['planning_snapshot'] = dict(product_id=product.id, product_version=product.version,
                                    daily_capacity=change['daily_capacity'], transport_days=change['transport_days'], materials=by_id)
    for demand in data['demands']:
        demand['procurement_days'] = by_id[demand['material_id']]['procurement_days']
        demand['purchase_start'] = purchase_dates[demand['material_id']]
    # Existing demand IDs/overrides/quantities and commercial/source snapshots stay frozen.
    data['planning_update_reason'] = f'合同内保存计划参数与采购周期；补入 {len(additions)} 种新增物料' if change['sync_materials'] else '合同内保存计划参数与采购周期'
    return ledger.save('order', data, order)
