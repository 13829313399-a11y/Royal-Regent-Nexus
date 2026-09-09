import pytest
from test_internal_quote_api import ALL_SECTION_CODES, create_payload, login, make_client
from test_internal_quote_painting_split import source


@pytest.mark.parametrize('component', [False, True])
def test_import_confirm_reload_manual_update_and_summary(monkeypatch, component):
    with make_client(monkeypatch) as client:
        factory = 'huakang-b' if component else 'huaxing'
        login(client, 'paint_split_owner', 'sales_customer_owner', 'sales-business', factory)
        payload = create_payload(suffix='SPLIT', participating_sections=ALL_SECTION_CODES)
        if component:
            payload.update(factory_id=factory, workshop_code='huakang-b-workshop', customer='JustPlay', pricing_components=['主体', '配件'])
        created = client.post('/api/internal-quotes', json=payload)
        assert created.status_code == 201, created.text
        base = f"/api/internal-quotes/{created.json()['id']}"
        preview = client.post(base + '/imports/painting/preview', files={'file': ('新喷油.xlsx', source(None, None))})
        assert preview.status_code == 201, preview.text
        batch = preview.json()
        confirm = {'revision': batch['target_revision'], 'mode': 'replace'}
        if component:
            confirm['component_assignments'] = {'rows:0': 'component-02'}
        response = client.post(base + f"/imports/{batch['batch_id']}/confirm", json=confirm)
        assert response.status_code == 200, response.text
        section = response.json()['section']
        assert section['calculation']['status'] == 'blocked'
        row = section['payload']['rows'][0]
        assert row['paint_cost_hkd'] is None and row['labor_cost_hkd'] is None
        row['paint_cost_hkd'] = '2'
        saved = client.put(base + '/sections/painting', json={'revision': section['revision'], 'payload': section['payload']})
        assert saved.status_code == 200, saved.text
        assert saved.json()['calculation']['totals']['painting_labor_hkd'] == '8.0000'
        loaded = next(s for s in client.get(base).json()['sections'] if s['department'] == 'painting')
        assert loaded['payload']['rows'][0]['paint_cost_hkd'] == '2'
        assert loaded['payload']['rows'][0]['labor_cost_hkd'] is None
        if component:
            assert loaded['payload']['rows'][0]['pricing_component_id'] == 'component-02'
        summary = client.get(base + '/summary')
        assert summary.status_code == 200, summary.text
        costs = {r['key']: r['value'] for r in summary.json()['rr2_cost_summary']['t3']}
        assert (costs['paint_material'], costs['painting_labor']) == ('2.0000', '8.0000')
