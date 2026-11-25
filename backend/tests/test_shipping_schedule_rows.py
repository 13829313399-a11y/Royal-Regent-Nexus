import json
from types import SimpleNamespace

from app.services.shipping_mail_service import expand_schedule_rows


def task(items: list[dict] | None, **overrides):
    base = dict(
        id='task-1', so_number='SHZ8265013', customer='ZURU', container_type='1*40HQ',
        port='盐田', destination_country='美国', planned_ship_date='2026-11-20',
        si_deadline='2026-11-18T17:00', cutoff_date='2026-11-19T12:00', status='review',
        items_json=json.dumps(items or [], ensure_ascii=False),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_same_code_with_two_contracts_expands_to_two_rows():
    rows = expand_schedule_rows([task([
        {'product_code': '77903TQ1', 'contract_no': 'CT-2026-001', 'quantity': 600},
        {'product_code': '77903TQ1', 'contract_no': 'CT-2026-002', 'quantity': 400},
    ])])

    assert [row['contract_no'] for row in rows] == ['CT-2026-001', 'CT-2026-002']
    assert [row['product_code'] for row in rows] == ['77903TQ1', '77903TQ1']
    assert [row['quantity'] for row in rows] == [600, 400]
    assert {row['task_id'] for row in rows} == {'task-1'}
    assert {row['so_number'] for row in rows} == {'SHZ8265013'}


def test_item_without_contract_keeps_the_row_with_an_empty_contract():
    rows = expand_schedule_rows([task([{'product_code': '40624', 'quantity': 5280}])])
    assert len(rows) == 1
    assert rows[0]['contract_no'] == ''
    assert rows[0]['product_code'] == '40624'


def test_task_without_items_still_renders_one_row():
    rows = expand_schedule_rows([task([])])
    assert len(rows) == 1
    assert rows[0]['product_code'] == '' and rows[0]['contract_no'] == ''
    assert rows[0]['so_number'] == 'SHZ8265013'


def test_non_dict_items_are_ignored():
    rows = expand_schedule_rows([task(['坏数据', {'product_code': 'A-1', 'contract_no': 'CT-1'}])])  # type: ignore[list-item]
    assert [row['product_code'] for row in rows] == ['A-1']


def test_rows_preserve_task_fields_for_the_table():
    rows = expand_schedule_rows([task([{'product_code': 'A-1', 'contract_no': 'CT-1', 'cbm': 1.5}])])
    row = rows[0]
    assert row['port'] == '盐田'
    assert row['destination_country'] == '美国'
    assert row['planned_ship_date'] == '2026-11-20'
    assert row['container_type'] == '1*40HQ'
    assert row['status'] == 'review'
    assert row['cbm'] == 1.5
