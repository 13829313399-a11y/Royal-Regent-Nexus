"""Synthetic, API-created settlements/payments attached to expanded production."""
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

from openpyxl import load_workbook
from sqlalchemy import delete
from sqlalchemy.orm import Session

from test_cutting_p5b_acceptance import (
    BASE, command, login, ok, sheet_records, export, snapshot_role,
    AuthRolePermission, AuthRoleBindingMetadata,
)
from test_cutting_settlement import basis, record, decision
from test_cutting_payments import save, read, decision as payment_decision


def validate_settlement_workbook(response, statement):
    assert response.headers['cache-control'] == 'no-store'
    with BytesIO(response.content) as stream:
        book = load_workbook(stream, read_only=True)
        try:
            check_settlement_book(book, statement)
        finally:
            book.close()


def check_settlement_book(book, statement):
    total = sheet_records(book, '结算汇总')[0]
    assert (total['币种'], total['验收结算套数'], total['含税应付金额']) == ('CNY', 10, '30.00')
    rows = sheet_records(book, '验收计费明细')
    assert len(rows) == 1
    row = rows[0]
    assert (row['订单明细ID'], row['任务ID'], row['验收单ID'], row['本次结算套数'], row['冻结金额']) == (
        statement['line_id'], 'external', statement['acceptance_id'], 10, '30.00')
    assert row['报价版本ID'] and row['验收事件ID']


def expand_financial_chains(p, count):
    # prepare_closed_order deliberately tests an accidental dual-duty grant.
    # Restore the registrar's exact frozen role before this load scenario.
    with Session(p.engine) as db:
        db.execute(delete(AuthRolePermission).where(AuthRolePermission.id == 'temporary-dual-duty'))
        db.flush()
        db.get(AuthRoleBindingMetadata, 'registrar').role_version_id = snapshot_role(db, 'registrar', 'fixture').id
        db.commit()
    statements = []
    for index in range(count):
        line_id = 'line-1' if index == 0 else f'http-capacity-{index}'
        login(p, 'supervisor')
        if index == 0:
            identifier = p.one
        else:
            value = basis(p)
            row = next(r for r in value['rows'] if r['line_id'] == line_id)
            ok(p.post(BASE+'/settlements/price', json=command(expected_version=value['revision'],
                line_id=line_id, task_id='external', context_token=row['context_token'],
                unit_price='3', currency='CNY', evidence='合成外发含税报价凭据')))
            value = basis(p)
            row = next(r for r in value['rows'] if r['line_id'] == line_id)
            identifier = uuid4().hex
            body = command(expected_version=value['revision'], document_id=identifier, month='2026-10',
                basis_token=value['basis_token'], selections=[dict(line_id=line_id,
                acceptance_id=row['acceptance_id'], sets=10)], vendor_evidence='合成外厂已核对凭据')
            preview = ok(p.post(BASE+'/settlement-preview', json=body))
            ok(p.post(BASE+'/settlements/save', json=body | {'vendor_confirmation_token':preview['confirmation_token']}))
            ok(decision(p, identifier, 'submit'))
            login(p, 'reviewer')
            ok(decision(p, identifier, 'confirm'))
        login(p, 'reviewer')
        value = record(p, identifier)
        assert value['state'] == 'confirmed' and value['data']['snapshot']['total'] == '30.00'
        acceptance = next(r for r in basis(p)['rows'] if r['line_id'] == line_id)['acceptance_id']
        statement = dict(document_id=identifier, line_id=line_id, acceptance_id=acceptance,
                         event_id=value['event_id'], snapshot=value['data']['snapshot'])
        book, _ = export(p, 'settlement', document_id=identifier, event_id=value['event_id'])
        try:
            check_settlement_book(book, statement)
        finally:
            book.close()
        login(p, 'registrar')
        payment_id = save(p, day='2026-11-03', allocations=[dict(settlement_id=identifier, amount='5.00')])
        ok(payment_decision(p, payment_id, 'submit'))
        login(p, 'reviewer')
        ok(payment_decision(p, payment_id, 'confirm'))
        payment = read(p, payment_id, month='2026-11')
        assert payment['data']['prepared_by'] == 'registrar'
        assert payment['history'][-1]['actor'] == 'reviewer' and not payment['data']['local_admin_acceptance']
        statement.update(payment_id=payment_id, payment_event_id=payment['event_id'], payment_snapshot=payment['data']['snapshot'])
        statements.append(statement)
        if (index+1) % 5 == 0:
            print(f'created financial chains: {index+1}/{count}', flush=True)
    return statements


def assert_payment_balances(value, count, active=False):
    assert len(value['rows']) == count
    assert len(value['totals']) == 1 and value['totals'][0]['currency'] == 'CNY'
    total = value['totals'][0]
    numbers = {k: Decimal(total[k]) for k in ('payable', 'paid', 'pending', 'unpaid', 'available')}
    assert numbers['payable'] == count*30
    assert numbers['unpaid'] == numbers['payable']-numbers['paid']
    assert numbers['available'] == numbers['unpaid']-numbers['pending']
    assert numbers['paid'] in ({Decimal(count*5), Decimal(count*5+1)} if active else {Decimal(count*5)})
    assert numbers['pending'] in ({Decimal(0), Decimal(1)} if active else {Decimal(0)})
    assert numbers['paid']+numbers['pending'] <= count*5+int(active)
    for key, number in numbers.items():
        assert sum(Decimal(row[key]) for row in value['rows']) == number
    for row in value['rows']:
        assert row['currency'] == 'CNY' and Decimal(row['payable']) == 30
        assert Decimal(row['paid']) in ({Decimal(5), Decimal(6)} if active else {Decimal(5)})
        assert Decimal(row['pending']) in ({Decimal(0), Decimal(1)} if active else {Decimal(0)})
        assert Decimal(row['unpaid']) == Decimal(row['payable'])-Decimal(row['paid'])
        assert Decimal(row['available']) == Decimal(row['unpaid'])-Decimal(row['pending']) >= 0


def verify_payment_book(p, statements):
    """Read actual XLSX, reconcile every current settlement and baseline payment."""
    login(p, 'reviewer')
    book, _ = export(p, 'payments', month='2026-11')
    try:
        rows = sheet_records(book, '当前全期结算余额')
        assert len(rows) == len(statements)
        for statement in statements:
            row = next(r for r in rows if r['结算单ID'] == statement['document_id'])
            assert (row['冻结结算版本ID'], row['有效应付'], row['已付核销'], row['未付余额'], row['待复核占用']) == (
                statement['event_id'], '30.00', '5.00', '25.00', '0.00')
            allocation = next(r for r in sheet_records(book, '所选月核销明细') if r['付款单ID'] == statement['payment_id'])
            assert (allocation['结算单ID'], allocation['原冻结结算版本ID'], allocation['分配金额']) == (
                statement['document_id'], statement['event_id'], '5.00')
    finally:
        book.close()
