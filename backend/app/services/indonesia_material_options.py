"""Visible starting choices and validation for the shared option library."""
from app.schemas.indonesia_materials import Input, Text, Positive
from typing import Literal
from decimal import Decimal
import hashlib
import json


def option_key(group, value):
    return hashlib.sha256(json.dumps([group, value.strip().casefold()], ensure_ascii=False).encode()).hexdigest()


class OptionIdentity(Input):
    group: Literal['category', 'customs_unit', 'unit', 'usage', 'currency', 'supplier', 'export_company']
    value: Text


class Option(OptionIdentity):
    status: Literal['active', 'inactive'] = 'active'
    billing_basis: Literal['quantity', 'weight'] = 'quantity'
    kg_per_unit: Positive = Decimal(1)


SUPPLIERS = ['华兴玩具制品（河源）有限公司', '华登玩具制品（河源）有限公司', '华康玩具制品（河源）有限公司',
             '深圳市伟利橡塑制品有限公司', '伯爵印刷（河源）有限公司', '新利達環球發展有限公司',
             '东莞市星徽纸品有限公司', '香港睿同科技有限公司']
CHOICES = {
    'category': ['彩盒/彩卡', '利宝说明书', '塑胶', '半成品', '电池'],
    'customs_unit': ['KGM', 'TNE', 'PCE'], 'unit': ['pcs'], 'usage': ['产品配件'],
    'currency': ['USD', 'HKD'], 'supplier': SUPPLIERS,
    'export_company': SUPPLIERS[:3] + ['新利達環球發展有限公司', '深圳市华胜益出口贸易有限公司'],
}


def defaults():
    return [dict(group=group, value=value, status='active',
                 billing_basis='weight' if group == 'customs_unit' and value in {'KGM', 'TNE'} else 'quantity',
                 kg_per_unit='1000' if group == 'customs_unit' and value == 'TNE' else '1')
            for group, values in CHOICES.items() for value in values]


def automatic_billing(unit, records):
    # Store the selected rule in each material/purchase snapshot, never recompute old receipts.
    key = unit.upper()
    choices = {item['value'].upper(): item for item in defaults() if item['group'] == 'customs_unit'}
    choices.update({row.data['value'].upper(): row.data for row in records if row.data['group'] == 'customs_unit'})
    from app.services.indonesia_material_calculations import require
    item = choices.get(key)
    require(item is not None and not item.get('deleted') and item['status'] == 'active', '请先在基础选项中维护并启用该报关单位的计价规则', 422)
    return dict(billing_unit=unit, billing_basis=item['billing_basis'],
                billing_factor=str(item['kg_per_unit']) if item['billing_basis'] == 'weight' else '1')
