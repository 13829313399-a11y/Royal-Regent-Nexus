"""Workspace projections on isolated synthetic SQLite; never original stores."""
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from test_cutting_ops import client, BASE, user, create, command
from test_cutting_orders import flow
from test_cutting_planning import planned, resource, task, save, publish
from test_cutting_materials import bridge
from test_cutting_usage import custody, consume, write
from test_cutting_reporting import production, send, ok
from test_cutting_settlement import fees, price as fee_price, save as fee_save, decision, accountant
from test_cutting_payments import paid_setup, save as payment_save, decision as payment_decision, reviewer
from app.models.cutting_material_usage import CuttingMaterialEvent
from app.models.warehouse_operations import WarehouseOperation


def get(p, path, **params):
    response = p.get(BASE+'/workspace/'+path, params={'factory_id':'huakang-c', **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_planning_counts_current_publication_not_new_draft(planned):
    p, _ = planned
    ref = resource(p)
    assert save(p, [task(ref)]).status_code == 200
    assert get(p, 'planning')['stats'] == dict(total=1, scheduled=0, unscheduled=1, partial=0, review=0)
    assert publish(p).status_code == 200
    current = get(p, 'planning')
    assert current['stats']['scheduled'] == 1
    assert save(p, [task(ref, days=[])], reason='调整已发布排期').status_code == 200
    assert get(p, 'planning')['stats']['scheduled'] == 1
    assert get(p, 'planning', bucket='unscheduled')['total'] == 0
    assert get(p, 'planning', page=2)['stats'] == current['stats']
    assert get(p, 'planning', page=2)['data'] == []
    for state in ('unplanned', 'partial', 'published', 'pending_actual', 'review'):
        summary = get(p, 'planning', plan_status=state)
        ledger = p.get(BASE+'/orders', params={'factory_id':'huakang-c','plan_status':state}).json()
        assert summary['stats']['total'] == ledger['total']
        assert summary['stats']['total'] == summary['stats']['scheduled']+summary['stats']['unscheduled']


def test_inventory_preserves_signed_balance_and_has_no_costs(custody):
    p=custody
    consume(p)
    with Session(p.engine) as db:
        before=(db.scalar(select(func.count()).select_from(WarehouseOperation)),
                db.scalar(select(func.count()).select_from(CuttingMaterialEvent)))
    value=get(p,'inventory')
    assert value['total']==1
    row=value['data'][0]
    assert row['received_quantity']=='4' and row['remaining_quantity']=='1.5'
    assert row['consumed_quantity']=='2' and row['loss_quantity']=='0.5'
    assert 'price' not in row and 'normal_cost' not in row
    assert value['units']['米']['remaining_quantity']=='1.5'
    assert get(p,'inventory',execution='outsourced')['total']==0
    grouped=get(p,'inventory',view='orders')
    assert grouped['total']==1 and grouped['data'][0]['issue_count']==1
    assert grouped['units']==value['units']
    with Session(p.engine) as db:
        assert before==(db.scalar(select(func.count()).select_from(WarehouseOperation)),
                        db.scalar(select(func.count()).select_from(CuttingMaterialEvent)))


def test_activity_factory_cost_permissions_and_linked_warehouse(custody):
    p=custody
    consume(p)
    write(p,'price',issue_id=p.issue_id,unit_cost='3',currency='CNY',price_reference='合成成本凭据不可泄漏')
    value=get(p,'activity',source='material')
    assert any(row['action']=='price' for row in value['data'])
    warehouse=get(p,'activity',source='warehouse')
    assert {'REQUEST','ISSUE','CUTTING_RECEIPT'} <= {r['action'] for r in warehouse['data']}
    assert all(row['line_id']=='line-1' for row in warehouse['data'])
    order_no=warehouse['data'][0]['order_no']
    assert order_no
    assert get(p,'activity',source='warehouse',order_q=order_no)['total']==warehouse['total']
    assert get(p,'activity',source='warehouse',order_q='does-not-exist')['total']==0
    business_month=warehouse['data'][0]['business_day'][:7]
    assert get(p,'activity',source='warehouse',month=business_month)['total']>0
    assert get(p,'activity',source='warehouse',month='2000-01')['total']==0
    assert p.get(BASE+'/workspace/activity',params={'factory_id':'huakang-c','month':'2026-99'}).status_code==422
    p.cutting_auth['user']=user('read')
    assert not any(row['action']=='price' for row in get(p,'activity',source='material')['data'])
    assert get(p,'activity',q='合成成本凭据不可泄漏')['total']==0
    assert get(p,'activity',order_q=order_no,q='合成成本凭据不可泄漏')['total']==0
    assert p.get(BASE+'/workspace/costs',params={'factory_id':'huakang-c'}).status_code==403
    assert p.get(BASE+'/workspace/activity',params={'factory_id':'huaxing'}).status_code==422
    assert p.get(BASE+'/workspace/activity?factory_id=huakang-c&factory_id=huakang-c').status_code==422
    p.cutting_auth['user']=user('read',factory='huaxing')
    assert p.get(BASE+'/workspace/activity',params={'factory_id':'huakang-c'}).status_code==403


def test_cost_summary_keeps_missing_price_and_currency(custody):
    p=custody;consume(p)
    assert get(p,'costs')['pending_pricing']==1
    assert get(p,'costs')['currencies']=={}
    write(p,'price',issue_id=p.issue_id,unit_cost='3.125',currency='HKD',price_reference='合成原批次成本凭据')
    result=get(p,'costs')
    assert result['currencies']=={'HKD':{'normal':'6.25','loss':'1.56','completed':None,'wip':None}}
    assert result['pending_pricing']==0


def test_master_summary_counts_entities_not_revisions(client):
    create(client)
    assert get(client,'masters')==dict(bom=0,draft=0,material=1,resource=0)
    assert get(client,'activity',source='master')['total']==1
    assert get(client,'activity',source='master',order_q='no-order-schema')['total']==0


def test_payment_log_follows_original_settlement_order_and_permissions(paid_setup):
    p=paid_setup
    document=payment_save(p)
    ok(payment_decision(p,document,'submit'));reviewer(p);ok(payment_decision(p,document,'confirm'))
    from app.models.customer_order_ledger import OrderLedgerLine
    with Session(p.engine) as db:
        order_no=db.get(OrderLedgerLine,'line-1').reference_no
    result=get(p,'activity',source='payment',order_q=order_no,month='2026-10')
    assert any(row['document_id']==document and row['action']=='confirm' for row in result['data'])
    assert get(p,'activity',source='payment',order_q=order_no,month='2026-09')['total']==0
    assert get(p,'activity',source='payment',order_q='missing-order')['total']==0
    p.cutting_auth['user']=user('read','settlement_read')
    assert get(p,'activity',source='payment',order_q=order_no)['total']==0


def test_activity_fence_rejects_append_between_pages(client):
    first=get(client,'activity')
    create(client)
    response=client.get(BASE+'/workspace/activity',params={
        'factory_id':'huakang-c','page':2,'expected_token':first.get('token','missing')})
    assert response.status_code==409


def test_settlement_price_trace_and_historical_freeze(fees):
    p=fees
    original=fee_price(p, '2.50')
    prices=get(p,'activity',source='settlement')
    row=next(row for row in prices['data'] if row['id']==original['id'])
    assert row['month'] is None
    assert row['price_evidence']==dict(line_id='line-1',task_id='external',unit_price='2.50',
        currency='CNY',evidence='外厂盖章含税报价单')
    doc=fee_save(p)
    ok(decision(p,doc,'submit'));accountant(p);ok(decision(p,doc,'confirm'))
    from app.models.customer_order_ledger import OrderLedgerLine
    with Session(p.engine) as db:
        order_no=db.get(OrderLedgerLine,'line-1').reference_no
    filtered=get(p,'activity',source='settlement',order_q=order_no,month='2026-10')
    assert any(r['action']=='confirm' for r in filtered['data'])
    assert not any(r['action']=='price' for r in filtered['data'])  # no invented business date
    assert get(p,'activity',source='settlement',order_q='missing-order')['total']==0
    frozen=get(p,'months/2026-10')['frozen']
    assert len(frozen)==1 and frozen[0]['valid'] is True
    ok(decision(p,doc,'reopen'))
    assert get(p,'months/2026-10')['frozen'][0]['valid'] is False
    p.cutting_auth['user']=user('read')
    assert get(p,'activity',source='settlement')['data']==[]
    assert get(p,'months/2026-10')['frozen']==[]


def test_task_board_uses_published_day_and_explicit_readiness(planned):
    p,_=planned
    # The planning fixture deliberately has no reporting schema.
    response=p.get(BASE+'/workspace/tasks',params={'factory_id':'huakang-c','day':'2026-10-15'})
    assert response.status_code==503


def test_board_zero_report_draft_external_claim_and_outstanding(production):
    p=production
    day='2026-10-15'
    initial=get(p,'tasks',day=day)
    assert initial['stats']['tasks']==2 and initial['stats']['planned']==50
    assert initial['stats']['reported']==0
    ok(send(p,'save',sets=0))
    assert get(p,'tasks',day=day)['stats']['reported']==0
    # A separate effective zero is still a report, and an external claim is not completion.
    ok(send(p,sets=0))
    ok(send(p,task_id='external',sets=10))
    result=get(p,'tasks',day=day)
    assert result['stats']['reported']==2 and result['stats']['unreported']==0
    assert result['stats']['completed']==0
    ok(send(p,task_id='external',kind='return',sets=8))
    abnormal=get(p,'tasks',day=day,scope='abnormal')
    external=next(r for r in abnormal['data'] if r['task_id']=='external')
    assert '外发收回待验收' in external['reasons']
    assert len({(r['line_id'],r['task_id']) for r in abnormal['data']})==abnormal['total']
    assert get(p,'tasks',day=day,page=2)['stats']==get(p,'tasks',day=day)['stats']


def test_activity_sorts_real_instants_across_timezones(client):
    from app.models.cutting_ops import CuttingMaster, CuttingRevision
    with Session(client.engine) as db:
        for identifier, time in [('later','2026-10-20T02:00:00+00:00'),('earlier','2026-10-20T09:00:00+08:00')]:
            db.add(CuttingMaster(id=identifier,factory_id='huakang-c',kind='material',code=identifier,version=1))
            db.flush()
            db.add(CuttingRevision(master_id=identifier,version=1,status='active',data={},actor_id='test',
                created_at=time,reason='timezone test'))
        db.commit()
    assert [r['id'] for r in get(client,'activity')['data']]==['later','earlier']
