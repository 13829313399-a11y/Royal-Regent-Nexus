"""Read-only reconciliation groups; never allocate material costs to output sets."""
from copy import deepcopy

from app.services import cutting_usage as usage


def issue(identifier, *, unit='米', revision=1, task='t1', resource='r1', price='HKD', normal='0.01', loss='0.00'):
    return dict(issue_id=identifier, reversed=False, context=dict(dispatch_id='d1', bom_id='b1', bom_version=1,
        task_id=task, task_name='裁剪任务', resource_id=resource, resource_version=1, resource_name='本厂裁床',
        execution='internal', item_code='M1', item_name='蓝布', unit=unit,
        warehouse_material=dict(id='material1', revision=revision, spec='A', color='蓝', unit=unit)),
        received_quantity='2', returned_quantity='0', consumed_quantity='1', loss_quantity='0.1', remaining_quantity='0.9',
        price=dict(data=dict(entry=dict(currency=price))) if price else None,
        normal_cost=normal if price else None, loss_cost=loss if price else None)


def test_summary_keeps_currency_units_and_material_revisions_separate():
    rows=[issue('i1'), issue('i2', price='CNY', normal='0.02', loss='0.01'),
          issue('i3', unit='码'), issue('i4', revision=2)]
    original=deepcopy(rows)
    result=usage.cost_summary(rows)
    assert rows==original
    assert len(result['tasks'])==1 and len(result['materials'])==3
    assert result['tasks'][0]['costs']=={
        'HKD':dict(normal='0.03', loss='0.00', total='0.03'),
        'CNY':dict(normal='0.02', loss='0.01', total='0.03')}
    assert result['materials'][0]['consumed_quantity']=='2'
    assert result['materials'][0]['loss_quantity']=='0.2'


def test_summary_distinguishes_unpriced_use_known_zero_and_unused_issues():
    zero=issue('zero', normal='0.00', loss='0.00')
    pending=issue('pending', price=None)
    unused=issue('unused', price=None)
    unused.update(consumed_quantity='0', loss_quantity='0', remaining_quantity='2')
    reversed_issue=issue('reversed', normal='999.99')
    reversed_issue['reversed']=True
    result=usage.cost_summary([zero,pending,unused,reversed_issue])
    task=result['tasks'][0]
    assert task['issue_count']==3 and task['pending_pricing']==1
    assert task['costs']=={'HKD':dict(normal='0.00',loss='0.00',total='0.00')}
    material=result['materials'][0]
    assert material['pending_quantity']=='1.1' and material['pending_pricing']==1
    assert material['remaining_quantity']=='3.8'


def test_summary_does_not_merge_reassigned_executors_or_frozen_bom_versions():
    other_bom=issue('i3')
    other_bom['context']['bom_version']=2
    result=usage.cost_summary([issue('i1'),issue('i2',resource='r2'),other_bom])
    assert len(result['tasks'])==3
    assert len(result['materials'])==1
    assert result['materials'][0]['costs']['HKD']['normal']=='0.03'


def test_empty_summary_has_no_fabricated_zero_cost_rows():
    assert usage.cost_summary([])==dict(tasks=[],materials=[])


def test_summary_sums_six_place_quantities_exactly_without_float_conversion():
    tiny=issue('tiny',price=None)
    tiny.update(received_quantity='0.000003',returned_quantity='0.000001',consumed_quantity='0.000001',
                loss_quantity='0',remaining_quantity='0.000001')
    result=usage.cost_summary([tiny,tiny])['materials'][0]
    assert result['received_quantity']=='0.000006'
    assert result['pending_quantity']=='0.000002'
