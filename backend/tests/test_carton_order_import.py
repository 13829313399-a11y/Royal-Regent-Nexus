"""New order imports: shared parsing, whole-order selection and canonical creation."""
from copy import deepcopy
from decimal import Decimal
from io import BytesIO
from uuid import uuid4
import json

import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy import select
from test_molding_sample_api import make_client, login_as, ensure_test_user
from test_carton_procurement_api import _ensure_dickie_customer
from test_carton_special_requests import ok
from test_carton_supplier_portal import grant_supplier_permissions

ROOT = '/api/carton-unified-orders/order-import'
FACTORY = 'huaxing'


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)
    monkeypatch.setenv('ONLINE_DOCUMENTS_ENABLED', 'false')


def workbook(rows, *, mode='REGULAR', title='客户自己的订单', header=3, labels=None, second=False):
    from app.services.carton_order_import_file import fields
    keys = [k for k, _, _ in fields(mode)]
    names = dict((k, label) for k, label, _ in fields(mode))
    keys.reverse()  # Every test uses a non-template column order.
    book = Workbook(); sheet = book.active; sheet.title = title
    for _ in range(header - 1): sheet.append(['客户自有表格说明'])
    sheet.append([(labels or {}).get(k, names[k]) for k in keys])
    for row in rows: sheet.append([row.get(k, '') for k in keys])
    if second:
        other = book.copy_worksheet(sheet); other.title = '第二张订单表'
    output = BytesIO(); book.save(output); book.close()
    return output.getvalue()


def regular(**changes):
    return dict(customer='Dickie', contract_no='IMPORT-001', item_no='000123', customer_po='PO-001',
                product_quantity='1201', order_date='2026-10-30', customer_due_date='2026-11-10',
                packaging_type='外箱', paper_quality='A33', specification='20*10*8', dimension_unit='cm',
                usage_quantity='12', unit='个', **changes)


def special_row(**changes):
    row = dict(group='A', kind='杂单', packaging_type='外箱', paper_quality='A33', specification='20*10*8',
               dimension_unit='cm', quantity='12.125', unit='个', required_date='2026-11-10')
    return row | changes


def post(client, action, content, body):
    return client.post(ROOT + '/' + action, data={'body': json.dumps(body)}, files={'file': ('自有文件.xlsx', content)})


def read_body(client, content, mode='REGULAR', **options):
    data = ok(post(client, 'read', content, dict(factory_id=FACTORY, mode=mode, **options)))
    return dict(factory_id=FACTORY, mode=mode, **{key: data[key] for key in ('fingerprint', 'sheet', 'header_row', 'mapping', 'rows')})


def checked(client, content, body, selected=None):
    preview = ok(post(client, 'preview', content, body))
    return dict(**body, request_id=uuid4().hex, preview_fingerprint=preview['preview_fingerprint'],
                selected_groups=selected or [g['id'] for g in preview['groups'] if g['status'] == 'READY']), preview


def setup(client, monkeypatch, *, fast=True):
    login_as(client, 'admin'); _ensure_dickie_customer(client); login_as(client, 'admin')
    if fast:
        from app.services import carton_file_jobs
        from app.services.carton_order_import_file import read
        original = carton_file_jobs.run_file_job
        monkeypatch.setattr(carton_file_jobs, 'run_file_job', lambda op, *args: read(*args) if op == 'order_import_read' else original(op, *args))


def test_parser_aliases_sheet_header_ambiguous_columns_and_limits():
    from app.services.carton_order_import_file import read
    data = workbook([regular()], labels={'contract_no': '合同编号', 'item_no': '产品编号', 'quantity': '数量'}, second=True)
    parsed = read(data, 'REGULAR')
    assert parsed['header_row'] == 3 and len(parsed['sheets']) == 2
    assert parsed['rows'][0]['data']['item_no'] == '000123'
    assert 'quantity' not in parsed['mapping']
    quantity_column = next(c['index'] for c in parsed['columns'] if c['label'] == '数量')
    mapped = read(data, 'REGULAR', '第二张订单表', 3, parsed['mapping'] | {'quantity': quantity_column})
    assert mapped['sheet'] == '第二张订单表'
    with pytest.raises(HTTPException):
        read(data, 'REGULAR', mapping={'customer': 1, 'item_no': 1})
    with pytest.raises(HTTPException):
        read(workbook([regular() | {'quantity': '=1+1'}]), 'REGULAR')
    with pytest.raises(HTTPException):
        read(workbook([regular()] * 501), 'REGULAR')


def test_real_worker_regular_calculated_pairing_replay_and_source_evidence(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client, monkeypatch, fast=False)
        card = regular() | dict(packaging_type='平卡', usage_quantity='', carton_source_row='4', per_carton_quantity='2', unit='张')
        content = workbook([regular() | {'quantity': '105'}, card])
        body = read_body(client, content)
        command, preview = checked(client, content, body)
        assert preview['groups'][0]['quantities'] == ['105.0000', '210.0000']
        result = ok(post(client, 'confirm', content, command))
        assert result['count'] == 1
        assert ok(post(client, 'confirm', content, command)) == result
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder, CartonOrderLine, CartonAuditEvent, CartonPurchaseOrderIssue, CartonReceipt
        with SessionLocal() as db:
            order = db.get(CartonOrder, result['orders'][0]['id'])
            assert order.status == 'CONFIRMED' and order.due_date == '2026-11-07'
            assert order.product_order_quantity == Decimal('1201')
            assert len(list(db.scalars(select(CartonOrderLine).where(CartonOrderLine.order_id == order.id)))) == 2
            assert db.scalar(select(CartonPurchaseOrderIssue)) is None and db.scalar(select(CartonReceipt)) is None
            events = list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.event_type == 'NEW_ORDER_IMPORTED')))
            assert len(events) == 2 and all(json.loads(e.detail_json)['sheet'] == '客户自己的订单' for e in events)
        changed = deepcopy(command); changed['rows'][0]['data']['note'] = '不同内容'
        assert post(client, 'confirm', content, changed).status_code == 409
        duplicate = command | {'request_id': uuid4().hex}
        assert post(client, 'confirm', content, duplicate).status_code == 409


def test_partial_import_whole_groups_then_correct_remaining_without_duplicate(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client, monkeypatch)
        content = workbook([regular(), regular() | {'packaging_type': '内盒', 'specification': ''},
                            regular() | {'contract_no': 'IMPORT-002', 'customer_po': '', 'usage_quantity': '', 'product_quantity': '', 'quantity': '7.125'}])
        body = read_body(client, content)
        command, preview = checked(client, content, body)
        assert [g['status'] for g in preview['groups']] == ['INVALID', 'READY']
        result = ok(post(client, 'confirm', content, command)); assert result['count'] == 1
        missing = deepcopy(body); missing['rows'].pop(1)
        assert post(client, 'preview', content, missing).status_code == 422
        body['rows'][1]['data']['specification'] = '10*8*6'
        command, preview = checked(client, content, body)
        assert [g['status'] for g in preview['groups']] == ['READY', 'IMPORTED']
        assert ok(post(client, 'confirm', content, command))['count'] == 1


def test_conflicting_headers_and_attempt_to_split_original_group_are_blocked(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client, monkeypatch)
        content = workbook([regular(), regular() | {'product_quantity': '1500'}])
        body = read_body(client, content)
        _, preview = checked(client, content, body)
        assert preview['groups'][0]['status'] == 'INVALID'
        body['rows'][1]['data']['customer_po'] = 'DIFFERENT'
        _, preview = checked(client, content, body)
        assert all('不能拆开' in g['errors'][0] for g in preview['groups'])


def test_special_same_import_pipeline_draft_partial_and_legacy_claim(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client, monkeypatch)
        content = workbook([special_row(), special_row(group='B', specification='')], mode='SPECIAL', title='新建需求')
        body = read_body(client, content, 'SPECIAL')
        command, preview = checked(client, content, body)
        assert [g['status'] for g in preview['groups']] == ['READY', 'INVALID']
        result = ok(post(client, 'confirm', content, command))
        row = ok(client.get('/api/carton-special-requests/' + result['orders'][0]['id'], params={'factory_id': FACTORY}))
        assert row['status'] == 'SUBMITTED' and not row['customer_code'] and not row['workshop_id']
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        with SessionLocal() as db:
            events = list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.event_type == 'NEW_ORDER_IMPORTED')))
            assert len(events) == 1 and events[0].id.startswith('CAE-DI-')
            assert json.loads(events[0].detail_json)['source_row'] == 4


def test_atomic_rollback_and_changed_rules_require_new_preview(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client, monkeypatch)
        content = workbook([regular(), regular() | {'contract_no': 'SECOND'}])
        body = read_body(client, content); command, _ = checked(client, content, body)
        from app.services import carton_procurement as core
        create = core.create_order
        def fail_last(db, payload, user, **kwargs):
            if payload.contract_no == 'SECOND': raise HTTPException(409, '最后一单冲突')
            return create(db, payload, user, **kwargs)
        monkeypatch.setattr(core, 'create_order', fail_last)
        assert post(client, 'confirm', content, command).status_code == 409
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder
        with SessionLocal() as db: assert db.scalar(select(CartonOrder)) is None
        monkeypatch.setattr(core, 'create_order', create)
        rules = core.master_data.due_rules
        monkeypatch.setattr(core.master_data, 'due_rules', lambda *args: rules(*args) | {'lead_days': 5})
        assert post(client, 'confirm', content, command).status_code == 409
        command, preview = checked(client, content, body)
        assert preview['groups'][0]['due_date'] == '2026-11-05'
        assert ok(post(client, 'confirm', content, command))['count'] == 2


def test_customer_scope_factory_and_original_session_rechecked_under_lock(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client, monkeypatch)
        content = workbook([regular()]); body = read_body(client, content); command, _ = checked(client, content, body)
        from app.services import carton_special_requests as service
        from app.models.auth import AuthSession
        lock = service.locked_actor
        def revoke(db, user, factory):
            actor = lock(db, user, factory)
            for session in db.scalars(select(AuthSession).where(AuthSession.user_id == actor.id)): session.status = 'revoked'
            db.flush(); return actor
        monkeypatch.setattr(service, 'locked_actor', revoke)
        assert post(client, 'confirm', content, command).status_code == 401
        monkeypatch.setattr(service, 'locked_actor', lock)
        login_as(client, 'warehouse_keeper')
        assert post(client, 'read', content, {'factory_id': 'huakang-a', 'mode': 'REGULAR'}).status_code == 403
        from app.db import SessionLocal
        from app.models.carton_customer_assignment import CartonCustomerAssignment
        from sqlalchemy import delete
        with SessionLocal() as db:
            from app.models.auth import AuthUser
            actor_id = db.scalar(select(AuthUser.id).where(AuthUser.username == 'warehouse_keeper'))
            db.execute(delete(CartonCustomerAssignment).where(CartonCustomerAssignment.user_id == actor_id)); db.commit()
        preview = ok(post(client, 'preview', content, body))
        assert preview['groups'][0]['status'] == 'INVALID'


def test_request_only_user_can_import_special_but_not_regular(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client, monkeypatch)
        ensure_test_user('engineer'); grant_supplier_permissions('user-engineer', ('carton_procurement:special_request_submit',))
        login_as(client, 'engineer')
        content = workbook([special_row()], mode='SPECIAL')
        body = read_body(client, content, 'SPECIAL'); command, _ = checked(client, content, body)
        assert ok(post(client, 'confirm', content, command))['count'] == 1
        assert post(client, 'read', content, {'factory_id': FACTORY, 'mode': 'REGULAR'}).status_code == 403


def test_blank_merged_identity_or_missing_mapping_cannot_leave_a_ready_sibling(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client, monkeypatch)
        for explicit_groups in (False, True):
            for missing in ('customer', 'contract_no', 'item_no', 'customer_po'):
                content = workbook([regular() | {'group': 'A' if explicit_groups else ''},
                                    regular() | {missing: '', 'packaging_type': '平卡', 'group': 'B' if explicit_groups else ''}])
                body = read_body(client, content)
                _, preview = checked(client, content, body)
                assert not any(g['status'] == 'READY' for g in preview['groups']), (missing, explicit_groups)
        content = workbook([regular(), regular() | {'packaging_type': '平卡'}])
        body = read_body(client, content)
        body['mapping'].pop('customer')
        body['rows'][1]['data']['customer'] = ''
        _, preview = checked(client, content, body)
        assert not any(g['status'] == 'READY' for g in preview['groups'])
        body['rows'][1]['data']['customer'] = 'Dickie'
        command, preview = checked(client, content, body)
        assert len(preview['groups']) == 1 and preview['groups'][0]['status'] == 'READY'
        assert ok(post(client, 'confirm', content, command))['count'] == 1


def test_explicit_groups_cannot_isolate_an_invalid_paper_of_the_same_regular_order(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client, monkeypatch)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonCustomer
        with SessionLocal() as db:
            customer = db.scalar(select(CartonCustomer).where(CartonCustomer.factory_id == FACTORY, CartonCustomer.customer_code == 'DICKIE'))
            customer.customer_name = '迪凯玩具'
            db.commit()
            customer_name = customer.customer_name
        rows = [regular() | {'group': 'A', 'specification': '', 'customer': customer_name},
                regular() | {'group': 'B', 'customer': 'DICKIE'}]
        for source in (rows, list(reversed(rows))):
            content = workbook(source); body = read_body(client, content)
            command, preview = checked(client, content, body, selected=['G-4'])
            assert all(g['status'] == 'INVALID' for g in preview['groups'])
            assert all('多个分组' in ' '.join(g['errors']) for g in preview['groups'])
            assert post(client, 'confirm', content, command).status_code == 422
        ambiguous_content = workbook([rows[0] | {'contract_no': ''}, rows[1]])
        ambiguous_body = read_body(client, ambiguous_content)
        _, ambiguous_preview = checked(client, ambiguous_content, ambiguous_body)
        assert not any(g['status'] == 'READY' for g in ambiguous_preview['groups'])
        for row in body['rows']:
            row['data'].update(group='A', specification='20*10*8', customer='DICKIE')
        command, preview = checked(client, content, body)
        assert len(preview['groups']) == 1 and preview['groups'][0]['status'] == 'READY'
        assert len(preview['groups'][0]['source_rows']) == 2
        assert ok(post(client, 'confirm', content, command))['count'] == 1


def test_legacy_demand_endpoint_rejects_paper_subset_and_changed_source_group(monkeypatch):
    from test_carton_batch_demand import workbook as old_workbook, preview as old_preview, confirm as old_confirm, import_body
    with make_client(monkeypatch) as client:
        setup(client, monkeypatch)
        content = old_workbook([
            ['A', '样板单', '', '外箱', 'A33', '20*10*8', 'cm', '10', '个', '2026-11-01', ''],
            ['A', '样板单', '', '平卡', 'A33', '20*10', 'cm', '20', '张', '2026-11-01', ''],
        ])
        body = import_body(old_preview(client, content))
        subset = deepcopy(body); subset['rows'].pop()
        assert old_confirm(client, content, subset).status_code == 422
        split = deepcopy(body); split['rows'][1]['group'] = 'B'
        assert old_confirm(client, content, split).status_code == 422
        assert ok(old_confirm(client, content, body))['count'] == 1


def test_special_supplier_change_invalidates_reviewed_preview(monkeypatch):
    with make_client(monkeypatch) as client:
        setup(client, monkeypatch)
        content = workbook([special_row()], mode='SPECIAL')
        body = read_body(client, content, 'SPECIAL'); command, _ = checked(client, content, body)
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonSupplier
        with SessionLocal() as db:
            supplier = db.scalar(select(CartonSupplier).where(CartonSupplier.factory_id == FACTORY))
            supplier.supplier_name = '供应商名称已修改'; db.commit()
        assert post(client, 'confirm', content, command).status_code == 409
        command, _ = checked(client, content, body)
        with SessionLocal() as db:
            supplier = db.scalar(select(CartonSupplier).where(CartonSupplier.factory_id == FACTORY))
            supplier.status = 'INACTIVE'; db.commit()
        assert post(client, 'confirm', content, command).status_code == 409
        result = ok(post(client, 'preview', content, body))
        assert result['groups'][0]['status'] == 'INVALID'
