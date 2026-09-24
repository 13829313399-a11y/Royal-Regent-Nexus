from copy import deepcopy
import importlib
from fastapi import HTTPException
from test_internal_quote_api import make_client, login, logout
from test_internal_quote_alternatives import create, fill, fork
from io import BytesIO
from PIL import Image


def current(client, quote):
    return client.get(f"/api/internal-quotes/{quote['id']}").json()


def section(quote, code):
    return next(row for row in quote['sections'] if row['department'] == code)


def change_screw(client, quote, price):
    quote = current(client, quote)
    row = section(quote, 'engineering')
    data = deepcopy(row['payload'])
    data['materials'][0]['unit_price_rmb'] = price
    response = client.put(f"/api/internal-quotes/{quote['id']}/sections/engineering", json={'revision': row['revision'], 'payload': data, 'reason': '更改螺丝价格'})
    assert response.status_code == 200, response.text
    return current(client, quote)


def request_for(client, source, targets, copies=False):
    return {'revision': current(client, source)['header_revision'],
            'family_revision': client.get(f"/api/internal-quotes/{source['id']}/alternatives").json()['revision'],
            'blocks': ['engineering.hardware'], 'reason': '统一螺丝规格与价格',
            'targets': [{'quote_id': target['id'], 'revision': current(client, target)['header_revision'], 'create_version': copies} for target in targets]}


def preview(client, source, body):
    response = client.post(f"/api/internal-quotes/{source['id']}/alternative-sync/preview", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def apply(client, source, body, expected=200):
    response = client.post(f"/api/internal-quotes/{source['id']}/alternative-sync/apply", json=body)
    assert response.status_code == expected, response.text
    return response.json()


def test_sync_preview_preserves_packaging_and_rejects_stale_atomic_batch(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, 'sync-owner', 'admin', '*', '*')
        source = fill(client, create(client, 'SYNC'))
        first = fork(client, source)
        second = fork(client, source, name='吸塑包装')
        source = change_screw(client, source, .8)
        body = request_for(client, source, [first, second])
        plan = preview(client, source, body)
        assert all(row['changed'] for row in plan['targets'])
        assert current(client, first) == first  # Preview is read-only.
        body['preview_token'] = plan['preview_token']
        second = change_screw(client, second, .7)
        apply(client, source, body, 409)
        assert current(client, first) == first
        body = request_for(client, source, [first, second])
        body['preview_token'] = preview(client, source, body)['preview_token']
        result = apply(client, source, body)
        assert len(result['targets']) == 2
        for quote in [first, second]:
            saved = current(client, quote)
            assert section(saved, 'engineering')['payload']['materials'][0]['unit_price_rmb'] == .8
            assert section(saved, 'sales')['payload'] == section(quote, 'sales')['payload']
            assert saved['reference_snapshot_id'] == quote['reference_snapshot_id']
            assert section(saved, 'engineering')['calculation_status'] == 'valid'
        apply(client, source, body, 409)  # Replaying an applied preview cannot apply twice.
        same = preview(client, source, request_for(client, source, [first]))
        assert not same['targets'][0]['changed']
        outside = fill(client, create(client, 'UNRELATED'))
        bad = request_for(client, source, [outside])
        response = client.post(f"/api/internal-quotes/{source['id']}/alternative-sync/preview", json=bad)
        assert response.status_code == 400


def test_issued_target_is_copied_and_original_export_unchanged(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, 'sync-issued', 'admin', '*', '*')
        source = fill(client, create(client, 'SYNC-ISSUED'))
        target = fork(client, source)
        record = client.post(f"/api/internal-quotes/{target['id']}/direct-issue", json={'revision': target['header_revision']})
        assert record.status_code == 200, record.text
        target = current(client, target)
        url = f"/api/internal-quotes/{target['id']}/exports/{record.json()['id']}/download"
        original = client.get(url).content
        source = change_screw(client, source, .9)
        body = request_for(client, source, [target])
        assert client.post(f"/api/internal-quotes/{source['id']}/alternative-sync/preview", json=body).status_code == 409
        body = request_for(client, source, [target], True)
        body['preview_token'] = preview(client, source, body)['preview_token']
        result = apply(client, source, body)['targets'][0]
        assert result['quote_id'] != target['id'] and result['version_label'] == 'B-V2'
        saved = current(client, {'id': result['quote_id']})
        assert saved['status'] == 'drafting'
        assert section(saved, 'engineering')['payload']['materials'][0]['unit_price_rmb'] == .9
        assert section(saved, 'sales')['payload'] == section(target, 'sales')['payload']
        assert current(client, target) == target
        assert client.get(url).content == original


def test_sync_rollback_and_permission_checks(monkeypatch):
    monkeypatch.setenv('AUTHZ_MODE', 'enforce')
    monkeypatch.setenv('AUTHZ_WRITES_ENABLED', 'true')
    with make_client(monkeypatch) as client:
        login(client, 'sync-atomic', 'admin', '*', '*')
        source = fill(client, create(client, 'SYNC-ATOMIC'))
        first = fork(client, source)
        second = fork(client, source, name='吸塑')
        source = change_screw(client, source, 1)
        body = request_for(client, source, [first, second], True)
        body['preview_token'] = preview(client, source, body)['preview_token']
        service = importlib.import_module('app.services.internal_quote_sync')
        original_save = service._save_section_in_transaction
        calls = []
        def fail_second(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2: raise HTTPException(400, '模拟第二目标保存失败')
            return original_save(*args, **kwargs)
        monkeypatch.setattr(service, '_save_section_in_transaction', fail_second)
        apply(client, source, body, 400)
        assert current(client, first) == first
        assert len(client.get(f"/api/internal-quotes/{source['id']}/alternatives").json()['items']) == 3
        logout(client)
        login(client, 'sync-outsider', 'sales_customer_supervisor', 'sales-business', 'huadeng')
        assert client.post(f"/api/internal-quotes/{source['id']}/alternative-sync/preview", json=body).status_code == 403
        assert client.post(f"/api/internal-quotes/{source['id']}/alternative-sync/apply", json=body).status_code == 403


def test_sync_mold_picture_is_idempotent(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, 'sync-picture', 'admin', '*', '*')
        source = fill(client, create(client, 'SYNC-PICTURE'))
        target = fork(client, source)
        data = BytesIO(); Image.new('RGB', (5, 5), 'blue').save(data, format='PNG')
        uploaded = client.post(f"/api/internal-quotes/{source['id']}/attachments", data={'department': 'engineering'}, files={'file': ('mold.png', data.getvalue(), 'image/png')})
        assert uploaded.status_code == 201, uploaded.text
        source = current(client, source)
        row = section(source, 'engineering')
        row['payload']['molds'] = [{'item': '车身', 'mold_no': 'M1', 'cost_rmb': 1200, 'quantity': 1, 'image_attachment_ids': [uploaded.json()['id']]}]
        response = client.put(f"/api/internal-quotes/{source['id']}/sections/engineering", json={'revision': row['revision'], 'payload': row['payload'], 'reason': '模具测试'})
        assert response.status_code == 200, response.text
        body = request_for(client, source, [target]); body['blocks'] = ['engineering.molds']
        body['preview_token'] = preview(client, source, body)['preview_token']
        apply(client, source, body)
        attachments = client.get(f"/api/internal-quotes/{target['id']}/attachments").json()
        assert len(attachments) == 1 and attachments[0]['id'] != uploaded.json()['id']
        body = request_for(client, source, [target]); body['blocks'] = ['engineering.molds']
        plan = preview(client, source, body)
        assert not plan['targets'][0]['changed']
        body['preview_token'] = plan['preview_token']
        assert not apply(client, source, body)['targets'][0]['changed']
        assert len(client.get(f"/api/internal-quotes/{target['id']}/attachments").json()) == 1


def test_sync_merge_preserves_scheme_owned_values_and_other_categories():
    from app.services.internal_quote_sync import _merge
    original = {'materials': [
        {'item': '螺丝', 'category': 'hardware', 'unit_price_rmb': .5, 'markup_override': 1.5, 'disney_description': 'target'},
        {'item': '牙箱', 'category': 'auxiliary', 'unit_price_rmb': 3, 'markup_override': 1.8}], 'molds': [{'item': '车身'}]}
    source = {'materials': [
        {'item': '螺丝', 'category': 'hardware', 'unit_price_rmb': .8, 'markup_override': 2, 'disney_description': 'source'},
        {'item': '垫片', 'category': 'hardware', 'unit_price_rmb': .2, 'markup_override': 3, 'disney_description': 'source-new'}]}
    result = _merge(original, source, 'engineering.hardware')
    screw = next(row for row in result['materials'] if row['item'] == '螺丝')
    assert screw == {**original['materials'][0], 'unit_price_rmb': .8}
    assert result['materials'][0] == original['materials'][1]
    washer = next(row for row in result['materials'] if row['item'] == '垫片')
    assert 'markup_override' not in washer and 'disney_description' not in washer
    assert result['molds'] == original['molds']
    assert original['materials'][0]['unit_price_rmb'] == .5
    original['materials'].append({**original['materials'][1], 'specification': '另一规格'})
    assert len(_merge(original, source, 'engineering.hardware')['materials']) == 4
    import pytest
    with pytest.raises(HTTPException, match='') as caught:
        _merge(original, {'materials': [source['materials'][0], {**source['materials'][0], 'specification': '不同规格'}]}, 'engineering.hardware')
    assert caught.value.status_code == 409
    old = {'groups': [{'name': '衣服', 'materials': [{'item': '布', 'unit_price_rmb': 1, 'exchange_rate': .9, 'markup': 1.2}]}]}
    new = {'groups': [{'name': '衣服', 'materials': [{'item': '布', 'unit_price_rmb': 2, 'exchange_rate': .8, 'markup': 2}]}]}
    material = _merge(old, new, 'sewing')['groups'][0]['materials'][0]
    assert material['unit_price_rmb'] == 2 and material['exchange_rate'] == .9 and material['markup'] == 1.2
