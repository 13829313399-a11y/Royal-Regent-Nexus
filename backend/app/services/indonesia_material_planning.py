"""Update planning defaults and one contract without regenerating frozen demand."""
from copy import deepcopy
from datetime import date, timedelta

from app.schemas.indonesia_materials import OrderPlan
from app.services.indonesia_material_calculations import require, production_plan


def save_order_plan(ledger, order, payload):
    change = OrderPlan.model_validate(payload).model_dump(mode='json')
    product = ledger.get(change['product_id'], 'product')
    require(product.version == change['product_version'], '货号资料已被更新，请重新核对计划参数')
    require((product.data['customer'], product.data['code'], product.data['unit']) ==
            (order.data['customer'], order.data['item_no'], order.data['unit']), '计划货号与本合同不一致', 422)
    demands = order.data['demands']
    require(bool(demands), '本合同尚无物料需求，请先维护货号用量并生成合同需求', 422)
    ids = [item['material_id'] for item in change['materials']]
    require(len(ids) == len(set(ids)) and set(ids) == {d['material_id'] for d in demands},
            '采购周期必须完整对应本合同物料，不能遗漏、重复或增加其他物料', 422)
    materials = []
    for item in change['materials']:
        material = ledger.get(item['material_id'], 'material')
        require(material.version == item['expected_version'], '物料资料已被更新，请重新核对采购周期')
        materials.append((material, item['procurement_days']))
    # Validate the calculation before any master write. All writes also share the command transaction.
    try:
        plan = production_plan(order.data['quantity'], change['daily_capacity'], order.data['delivery_date'], change['transport_days'])
        purchase_dates = {material.id: (date.fromisoformat(plan['required_date']) - timedelta(days=days)).isoformat()
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
    data['plan'] = plan
    data['planning_snapshot'] = dict(product_id=product.id, product_version=product.version,
                                    daily_capacity=change['daily_capacity'], transport_days=change['transport_days'], materials=by_id)
    for demand in data['demands']:
        demand['procurement_days'] = by_id[demand['material_id']]['procurement_days']
        demand['purchase_start'] = purchase_dates[demand['material_id']]
    # Demand identities, quantities, overrides, recipes, commercial snapshots and sources stay frozen.
    data['planning_update_reason'] = '合同内保存计划参数与采购周期'
    return ledger.save('order', data, order)
