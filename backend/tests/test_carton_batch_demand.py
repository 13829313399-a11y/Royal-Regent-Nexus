"""Batch demand boundaries: atomicity, replay, originals and import provenance."""
from copy import deepcopy
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import json

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook
from sqlalchemy import select
from test_molding_sample_api import make_client, login_as, ensure_test_user
from test_carton_unified_order_actions import sources, payload
from test_carton_special_requests import BASE, FACTORY, ok, command
from test_carton_supplier_portal import grant_supplier_permissions

ROOT = '/api/carton-unified-orders'


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)
    monkeypatch.setenv('ONLINE_DOCUMENTS_ENABLED', 'false')


def selected(client, refs):
    return ok(client.post(ROOT + '/selected', json={'factory_id': FACTORY, 'items': refs}))


def ready(client):
    *_, refs = sources(client)
    ok(client.post(ROOT + '/batch-actions', json=payload(refs)))
    entries = selected(client, refs)
    items = []
    for entry in entries:
        row = entry.get('order') or entry['special']
        items.append(dict(kind=entry['kind'], id=row.get('order_no') or row['id'], expected_revision=row['revision'],
            reason='客户增加需求', lines=[{'id': row['lines'][0]['id'], 'additional_quantity': '0.1250'}], new_lines=[]))
    return refs, entries, dict(factory_id=FACTORY, request_id=uuid4().hex, items=items)


def totals(entries):
    return [[Decimal(str(line.get('required_quantity', line.get('quantity')))) for line in (entry.get('order') or entry['special'])['lines']] for entry in entries]


def test_mixed_append_atomic_revision_and_replay(monkeypatch):
    with make_client(monkeypatch) as client:
        refs, before, body = ready(client)
        stale = deepcopy(body); stale['items'][-1]['expected_revision'] += 1
        assert client.post(ROOT + '/batch-append', json=stale).status_code == 409
        assert totals(selected(client, refs)) == totals(before)
        result = ok(client.post(ROOT + '/batch-append', json=body))
        assert result['count'] == 3
        assert totals(selected(client, refs)) == [[values[0] + Decimal('.125'), *values[1:]] for values in totals(before)]
        assert ok(client.post(ROOT + '/batch-append', json=body)) == result
        changed = deepcopy(body); changed['items'][0]['reason'] = '修改原请求内容'
        assert client.post(ROOT + '/batch-append', json=changed).status_code == 409


def test_append_new_paper_rolls_back_when_last_order_fails(monkeypatch):
    with make_client(monkeypatch) as client:
        refs, before, body = ready(client)
        body['items'][0]['new_lines'] = [dict(packaging_type='内盒', paper_quality='B33', specification='10*8*6', dimension_unit='cm', quantity='7', unit='个')]
        body['items'][-1]['lines'][0]['id'] = 'foreign-paper'
        assert client.post(ROOT + '/batch-append', json=body).status_code == 422
        assert totals(selected(client, refs)) == totals(before)
        body['items'][-1]['lines'][0]['id'] = before[-1]['special']['lines'][0]['id']
        ok(client.post(ROOT + '/batch-append', json=body))
        assert totals(selected(client, refs))[0][-1] == Decimal(7)


def test_append_scope_and_session_checked_under_lock(monkeypatch):
    with make_client(monkeypatch) as client:
        refs, before, body = ready(client)
        assert client.post(ROOT + '/batch-append', json={**body, 'factory_id': 'huakang-a'}).status_code in {403, 404}
        from app.services import carton_special_requests as special
        from app.models.auth import AuthSession
        original = special.locked_actor
        def revoke(db, user, factory):
            actor = original(db, user, factory)
            for session in db.scalars(select(AuthSession).where(AuthSession.user_id == actor.id)):
                session.status = 'revoked'
            db.flush()
            return actor
        monkeypatch.setattr(special, 'locked_actor', revoke)
        assert client.post(ROOT + '/batch-append', json=body).status_code == 401
        monkeypatch.setattr(special, 'locked_actor', original)
        login_as(client, 'admin')
        assert totals(selected(client, refs)) == totals(before)


def workbook(rows=None):
    book = load_workbook(Path(__file__).parents[1] / 'app/templates/carton-demand-template.xlsx')
    sheet = book['新建需求']
    for n, row in enumerate(rows or [
        ['A', '样板单', '001', '外箱', 'A33', '20*10*8', 'cm', '12.125', '个', '', '样板需求'],
        ['B', '杂单', '', '内盒', 'B33', '10*8*6', 'cm', '5', '个', '2026-11-01', ''],
    ], 2):
        for col, value in enumerate(row, 1): sheet.cell(n, col, value)
    output = BytesIO(); book.save(output); book.close()
    return output.getvalue()


def preview(client, content):
    return ok(client.post(ROOT + '/demand-import/preview', data={'factory_id': FACTORY}, files={'file': ('需求.xlsx', content)}))


def confirm(client, content, body):
    return client.post(ROOT + '/demand-import/confirm', data={'body': json.dumps(body)}, files={'file': ('需求.xlsx', content)})


def import_body(data):
    body = dict(factory_id=FACTORY, request_id=uuid4().hex, **deepcopy(data))
    body['rows'][0]['required_date'] = '2026-11-01'
    return body


def test_import_preview_edit_group_drafts_replay_and_duplicate_source(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        content = workbook(); data = preview(client, content)
        assert data['rows'][0]['item_no'] == '001' and not data['rows'][0]['required_date']
        body = import_body(data)
        result = ok(confirm(client, content, body))
        assert result['count'] == 2
        for item in result['orders']:
            row = ok(client.get(BASE + '/' + item['id'], params={'factory_id': FACTORY}))
            assert row['status'] == 'SUBMITTED'
            assert not row['customer_code'] and not row['workshop_id']
        assert ok(confirm(client, content, body)) == result
        duplicate = deepcopy(body); duplicate['request_id'] = uuid4().hex; duplicate['rows'][0]['group'] = 'RENAME'
        assert confirm(client, content, duplicate).status_code == 409
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        with SessionLocal() as db:
            events = list(db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.event_type == 'DEMAND_IMPORTED')))
            assert len(events) == 2


def test_import_last_create_failure_rolls_back_and_can_retry(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        content = workbook(); body = import_body(preview(client, content))
        from app.services import carton_special_requests as special
        original = special.create
        def fail_last(db, user, data, **kwargs):
            if data.kind == 'WORKSHOP_MISC': raise HTTPException(409, '模拟最后一组失败')
            return original(db, user, data, **kwargs)
        monkeypatch.setattr(special, 'create', fail_last)
        assert confirm(client, content, body).status_code == 409
        assert ok(client.get(ROOT, params={'factory_id': FACTORY}))['total'] == 0
        monkeypatch.setattr(special, 'create', original)
        assert ok(confirm(client, content, body))['count'] == 2


def test_import_invalid_formula_identity_group_and_precision(monkeypatch):
    from app.services.carton_demand_import import parse
    with pytest.raises(HTTPException, match=''):
        parse(workbook([['A', '样板单', '', '外箱', 'A33', '20*10*8', 'cm', '=1+1', '个', '2026-11-01', '']]))
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        content = workbook(); body = import_body(preview(client, content))
        for change in [lambda b: b['rows'][0].update(source_row=500), lambda b: b['rows'][0].update(quantity='1.00001'), lambda b: b['rows'][1].update(group='A')]:
            invalid = deepcopy(body); change(invalid)
            assert confirm(client, content, invalid).status_code == 422
        assert ok(client.get(ROOT, params={'factory_id': FACTORY}))['total'] == 0


def test_request_only_user_can_import_but_cannot_append(monkeypatch):
    with make_client(monkeypatch) as client:
        ensure_test_user('engineer')
        grant_supplier_permissions('user-engineer', ('carton_procurement:special_request_submit',))
        login_as(client, 'engineer')
        content = workbook(); body = import_body(preview(client, content))
        assert ok(confirm(client, content, body))['count'] == 2
