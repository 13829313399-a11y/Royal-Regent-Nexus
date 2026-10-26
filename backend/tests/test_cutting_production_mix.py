"""The mixed-load validator must reject duplicate facts and stale costs."""
from copy import deepcopy
import sqlite3

import pytest

from cutting_production_mix import ProductionMix, quantity, reconcile_totals, D


@pytest.fixture
def fixture():
    rows = [dict(line_id=f'http-capacity-{i}', issue_id=f'issue-{i}',
        context=dict(execution='internal',unit='米'), received_quantity='4', returned_quantity='0',
        consumed_quantity='2', loss_quantity='0.5', remaining_quantity='1.5', unsigned_quantity='0')
        for i in [3, 4]]
    costs = [dict(line_id=r['line_id'], normal={'HKD':'8'}, loss={'HKD':'2'},
        completed={'HKD':'4.8'}, wip={'HKD':'3.2'}, allocation_pending=0,pending_pricing=0) for r in rows]
    def read(path, **params):
        if path.endswith('/reports'):
            return dict(summary=dict(completed=25,actual_delivery=22))
        return dict(issues=[dict(issue_id='issue-4', price={'data':{'entry':{'unit_cost':'4','currency':'HKD'}}})])
    mix = ProductionMix(read, rows, costs, 1)
    inventory = dict(total=2, units={'米':dict(received_quantity='8',returned_quantity='0',
        consumed_quantity='4',loss_quantity='1',remaining_quantity='3',unsigned_quantity='0')}, data=deepcopy(rows))
    cost = dict(total=2,pending_pricing=0,currencies={'HKD':dict(normal='16',loss='4',completed='9.6',wip='6.4')}, data=deepcopy(costs))
    expected = {'inventory':(2,deepcopy(inventory['units']),[]), 'costs':(2,deepcopy(cost['currencies']),0)}
    return mix, inventory, cost, expected


@pytest.mark.parametrize('damage',['duplicate_use','untargeted_use','changed_loss'])
def test_inventory_checks_reject_duplicate_or_unrelated_material_changes(fixture,damage):
    mix, inventory, _, expected = fixture
    mix.validate_live('inventory',inventory,expected)
    if damage=='duplicate_use':
        inventory['units']['米']['consumed_quantity']='4.3'
        inventory['units']['米']['remaining_quantity']='2.7'
    elif damage=='untargeted_use':
        inventory['data'][0].update(consumed_quantity='2.1',remaining_quantity='1.4')
    else:
        inventory['units']['米']['loss_quantity']='1.1'
    with pytest.raises(AssertionError):mix.validate_live('inventory',inventory,expected)


@pytest.mark.parametrize('damage',['stale_allocation','duplicate_cost','changed_currency'])
def test_cost_checks_reject_stale_or_duplicate_amounts(fixture,damage):
    mix, _, cost, expected = fixture
    mix.validate_live('costs',cost,expected)
    if damage=='stale_allocation':cost['currencies']['HKD']['normal']='16.4'
    elif damage=='duplicate_cost':cost['currencies']['HKD']['normal']='17.2'
    else:cost['currencies']['CNY']=cost['currencies']['HKD']
    with pytest.raises(AssertionError):mix.validate_live('costs',cost,expected)


def test_writes_keep_per_order_correction_targets_and_reconcile_actual_history(fixture):
    mix, inventory, costs, expected = fixture
    posted=[]
    def get(name,path,**params):
        return dict(version=7,revision=8,tasks=[dict(task_id='task-1',plan_version=3)])
    def post(name,path,body):
        posted.append((name,path,body))
        return dict(document_id=f'usage-{len(posted)}')
    mix.write(0,0,get,post);mix.write(0,1,get,post)
    mix.write(1,0,get,post);mix.write(1,1,get,post)
    assert posted[0][2]['document_id']==posted[1][2]['document_id']
    assert [r[2]['entry']['sets'] for r in posted[:2]]==[1,2]
    assert posted[2][1].endswith('/post') and posted[3][1].endswith('/correct')
    assert posted[3][2]['document_id']=='usage-3'
    assert posted[3][2]['counted_remaining']=='1.3'
    inventory['data'][1].update(consumed_quantity='2.2',remaining_quantity='1.3')
    inventory['units']['米'].update(consumed_quantity='4.2',remaining_quantity='2.8')
    costs['data'][1].update(normal={'HKD':'8.8'},completed={'HKD':None},wip={'HKD':None},allocation_pending=1)
    costs['currencies']['HKD'].update(normal='16.8',completed=None,wip=None)
    mix.validate_live('inventory',inventory,expected);mix.validate_live('costs',costs,expected)
    def final_read(path,**params):
        if path.endswith('/reports'):
            return dict(summary=dict(completed=25,actual_delivery=24),documents=[dict(
                document_id=mix.handover_documents['http-capacity-3'],history=[{},{}])])
        return dict(documents=[dict(id='usage-3',voided=True,replaces_document_id=None,replaced_by_document_id='usage-4'),
            dict(id='usage-4',voided=False,replaces_document_id='usage-3',replaced_by_document_id=None)])
    result=mix.reconcile(final_read,inventory['data'],costs['data'],120)
    assert result['handover_orders']==result['usage_orders']==1
    assert result['normal_use_delta']=='0.2' and D(result['normal_cost_delta_hkd'])==D('.8')
    assert result['all_target_orders_exercised']
    with sqlite3.connect(':memory:') as db:
        for table in ['cutting_ops_production_events','cutting_ops_material_events']:
            db.execute('CREATE TABLE '+table+' (document_id TEXT)')
        identifier=mix.handover_documents['http-capacity-3']
        db.executemany('INSERT INTO cutting_ops_production_events VALUES (?)',[(identifier,)]*2)
        db.executemany('INSERT INTO cutting_ops_material_events VALUES (?)',[('usage-3',),('usage-3',),('usage-4',)])
        assert mix.verify_persisted(db)==dict(production_events=2,material_events=3)
        db.execute('INSERT INTO cutting_ops_production_events VALUES (?)',(identifier,))
        with pytest.raises(AssertionError):mix.verify_persisted(db)
    inventory['data'][1]['consumed_quantity']='2.4'
    with pytest.raises(AssertionError):mix.reconcile(final_read,inventory['data'],costs['data'],120)


def test_missing_order_coverage_cannot_be_counted_as_a_sustained_pass(fixture):
    mix, inventory, costs, _ = fixture
    mix.targets=[mix.targets[0]+[dict(line_id='missing-handover')],mix.targets[1]]
    mix.records=[[dict(line_id='http-capacity-3')],[dict(line_id='http-capacity-4')]]
    with pytest.raises(AssertionError,match='coverage'):
        mix.reconcile(lambda *a,**k:pytest.fail('must fail before final reads'),inventory['data'],costs['data'],120)


def test_quantity_formatting_preserves_integer_zero_digits():
    assert quantity(D('10.00'))=='10' and quantity(D('20'))=='20' and quantity(D('1.20'))=='1.2'


@pytest.mark.parametrize('damage',['inventory_total','cost_total','hidden_wip'])
def test_full_pagination_rejects_wrong_header_totals(fixture,damage):
    _, inventory, costs, _ = fixture
    reconcile_totals(inventory,inventory['data'],costs,costs['data'])
    if damage=='inventory_total':inventory['units']['米']['consumed_quantity']='4.1'
    elif damage=='cost_total':costs['currencies']['HKD']['normal']='16.4'
    else:costs['data'][1]['wip']['HKD']=None
    with pytest.raises(AssertionError):reconcile_totals(inventory,inventory['data'],costs,costs['data'])
