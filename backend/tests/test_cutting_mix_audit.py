"""Validators must reject wrong historical facts, not only wrong final totals."""
from copy import deepcopy
import pytest
from cutting_mix_audit import check_post, segmented_diagnostics, distribution


def sample(kind):
    entry = dict(day='2026-12-14', task_id='task-1', sets=2) if kind == 'handover' else dict(
        day='2026-12-14', issue_id='issue-1', consumed_quantity='0.2', loss_quantity='0', counted_remaining='1.3')
    body = dict(operation_id='operation-1', expected_version=3, reason='Synthetic check', document_id='document-1')
    body.update(entry=entry) if kind == 'handover' else body.update(entry)
    record = dict(line_id='line-1', command=body, document_id='document-1', replaces='old-document' if kind == 'usage' else None,
                  receipt=dict(id='document-1', version=5))
    event = dict(line_id='line-1', factory_id='huakang-c', actor_id='clerk', reason=body['reason'], action='post',
        created_at='2026-12-15T12:00:00Z', id='operation-1' if kind == 'handover' else 'document-1',
        document_id='document-1', version=4 if kind == 'handover' else 5,
        data=dict(entry=deepcopy(entry), replaces_document_id=record['replaces']))
    return record, event


@pytest.mark.parametrize('kind',['handover','usage'])
@pytest.mark.parametrize('field',['line_id','factory_id','actor_id','reason','action','created_at','id','version','day','quantity'])
def test_historical_field_corruption_is_rejected(kind, field):
    record, event = sample(kind)
    check_post(event, record, kind)
    if field == 'quantity':
        event['data']['entry']['sets' if kind == 'handover' else 'consumed_quantity'] = 999
    elif field == 'day':event['data']['entry']['day'] = '1900-01-01'
    else:event[field] = '' if field == 'created_at' else 'wrong'
    with pytest.raises(AssertionError):check_post(event, record, kind)


def timing_fixture():
    samples = [dict(request_id='a', endpoint='handover', seconds=1, started_seconds=1000),
               dict(request_id='b', endpoint='handover', seconds=3, started_seconds=1120)]
    requests = [dict(request_id=s['request_id'],sql_count=2,sql_seconds=.2,lock_seconds=.05,
        header_ready_seconds=s['seconds'], admission_seconds=.1,
        phases=[dict(name='outer',start=0,end=1),dict(name='inner',start=0,end=.5)]) for s in samples]
    return dict(requests=requests,lock_spans=[dict(request_id='a',hold_seconds=.3)]), samples


def test_even_sample_median_uses_both_middle_values():
    assert distribution([3,1])==dict(count=2,median=2,p95=3,maximum=3)


def test_windows_join_request_ids_and_keep_overlapping_costs_separate():
    diagnostic, samples = timing_fixture()
    result = segmented_diagnostics(diagnostic, samples)
    first,last = result['windows']
    assert first['window_start']==0 and last['window_start']==120
    assert first['lock_hold_upper_seconds']['maximum']==.3
    assert first['overlapping_phases']['outer']['maximum']==1
    assert first['overlapping_phases']['inner']['maximum']==.5
    assert last['client_seconds']['maximum']==3 and last['sql_count']['maximum']==2


@pytest.mark.parametrize('damage',['missing','duplicate','duplicate_client','negative'])
def test_incomplete_or_invalid_timing_cannot_silently_pass(damage):
    diagnostic,samples=timing_fixture()
    if damage=='missing':diagnostic['requests'].pop()
    elif damage=='duplicate':diagnostic['requests'].append(diagnostic['requests'][0])
    elif damage=='duplicate_client':samples.append(samples[0])
    else:samples[0]['seconds']=-1
    with pytest.raises(AssertionError):segmented_diagnostics(diagnostic,samples)
