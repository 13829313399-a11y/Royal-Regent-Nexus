"""Independent client/SQLite reconciliation and segmented diagnostic summaries."""
from collections import defaultdict
import json
import math
import sqlite3
from statistics import median


def check_post(event, record, kind):
    body = record['command']
    assert event['line_id'] == record['line_id'] and event['factory_id'] == 'huakang-c'
    assert event['actor_id'] == 'clerk' and event['reason'] == body['reason']
    assert event['action'] == 'post' and event['created_at']
    entry = event['data']['entry']
    expected = body['entry'] if kind == 'handover' else {k: v for k, v in body.items()
        if k not in {'factory_id', 'operation_id', 'expected_version', 'reason', 'document_id'}}
    for key, value in expected.items():
        assert entry[key] == value, (kind, key, entry[key], value)
    if kind == 'handover':
        assert event['id'] == body['operation_id']
        assert event['version'] == body['expected_version'] + 1
        assert event['document_id'] == body['document_id']
    else:
        assert event['id'] == record['receipt']['id'] == record['document_id']
        assert event['version'] == record['receipt']['version']
        assert event['version'] == body['expected_version'] + (2 if record['replaces'] else 1)
        assert event['data'].get('replaces_document_id') == record['replaces']


def audit_history(read, database, records):
    """Match commands -> immutable events -> API history, including old values."""
    db = sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    checked = 0
    try:
        for kind, rows, table in [('handover', records[0], 'cutting_ops_production_events'),
                                 ('usage', records[1], 'cutting_ops_material_events')]:
            by_line = defaultdict(list)
            for record in rows:
                by_line[record['line_id']].append(record)
            for line, commands in by_line.items():
                api = read('/orders/'+line+('/reports' if kind == 'handover' else '/usage'), **({'with_costs': True} if kind == 'usage' else {}))
                documents = {d['document_id' if kind == 'handover' else 'id']: d for d in api['documents']}
                for record in commands:
                    identifier = record['operation_id'] if kind == 'handover' else record['receipt']['id']
                    event = dict(db.execute('SELECT * FROM '+table+' WHERE id=?', (identifier,)).fetchone())
                    event['data'] = json.loads(event['data'])
                    check_post(event, record, kind)
                    receipt = db.execute('SELECT actor_id,action,result FROM cutting_ops_commands WHERE operation_id=?',
                                         (record['operation_id'],)).fetchone()
                    assert receipt['actor_id'] == 'clerk'
                    expected_action = 'report-post:' if kind == 'handover' else 'usage-'+('correct:' if record['replaces'] else 'post:')
                    assert receipt['action'] == expected_action+line
                    if kind == 'usage':
                        assert json.loads(receipt['result']) == record['receipt']
                    doc = documents[event['document_id']]
                    history = next(e for e in doc['history'] if e['id'] == event['id'])
                    if kind == 'handover':
                        assert history == {k: event[k] for k in ('id','version','document_id','action','data','actor_id','created_at','reason')}
                    else:
                        assert doc['entry'] == event['data']['entry']
                        assert doc['context'] == event['data']['context']
                        assert doc['actor'] == event['actor_name'] == 'clerk'
                        assert doc['reason'] == event['reason'] and doc['created_at'] == event['created_at']
                        assert history == dict(id=event['id'], action='post', version=event['version'], actor='clerk',
                            date=event['created_at'], reason=event['reason'], business_day=event['data']['entry']['day'])
                        assert doc['cost_at_post'] == event['data']['cost_at_post']
                        if record['replaces']:
                            old = documents[record['replaces']]
                            void = dict(db.execute('SELECT * FROM '+table+" WHERE document_id=? AND action='void'",
                                                   (record['replaces'],)).fetchone())
                            payload = json.loads(void['data'])
                            assert void['version'] == event['version']-1 and void['actor_id'] == 'clerk'
                            assert payload['replaced_by_document_id'] == event['document_id']
                            assert old['voided'] and old['replaced_by_document_id'] == event['document_id']
                            assert next(h for h in old['history'] if h['id'] == void['id']) == dict(
                                id=void['id'], action='void', version=void['version'], actor=void['actor_name'],
                                date=void['created_at'], reason=void['reason'], business_day=payload['entry']['day'])
                    checked += 1
        return dict(post_versions_checked=checked, command_event_api_matched=True)
    finally:
        db.close()


def distribution(values):
    values = sorted(values)
    assert values and all(math.isfinite(v) and v >= 0 for v in values)
    return dict(count=len(values), median=median(values),
                p95=values[math.ceil(len(values)*.95)-1], maximum=values[-1])


def segmented_diagnostics(diagnostic, samples, window=120):
    """SQL/phase timings overlap; retain each separately, never add as a total."""
    requests = {r['request_id']: r for r in diagnostic['requests'] if r['request_id']}
    assert len(requests) == len([r for r in diagnostic['requests'] if r['request_id']]), 'Duplicate server request identity'
    assert samples and len({s['request_id'] for s in samples}) == len(samples)
    assert all(s['request_id'] in requests for s in samples), 'Missing server timing'
    start = min(s['started_seconds'] for s in samples)
    spans = defaultdict(list)
    for span in diagnostic['lock_spans']:
        spans[span['request_id']].append(span)
    groups = defaultdict(list)
    for sample in samples:
        bucket = int((sample['started_seconds']-start)//window)
        groups[(bucket, sample['endpoint'])].append(sample)
    result = []
    for (bucket, endpoint), group in sorted(groups.items()):
        data = dict(window_start=bucket*window, window_seconds=window, endpoint=endpoint,
                    client_seconds=distribution([s['seconds'] for s in group]))
        for metric in ['sql_count','sql_seconds','lock_seconds','header_ready_seconds','admission_seconds']:
            data[metric] = distribution([requests[s['request_id']].get(metric, 0) for s in group])
        data['lock_hold_upper_seconds'] = distribution([sum(p['hold_seconds'] for p in spans[s['request_id']]) for s in group])
        phases = defaultdict(list)
        for sample in group:
            totals = defaultdict(float)
            for phase in requests[sample['request_id']]['phases']:
                totals[phase['name']] += phase['end']-phase['start']
            for name, duration in totals.items():
                phases[name].append(duration)
        data['overlapping_phases'] = {name: distribution(v) for name, v in sorted(phases.items())}
        result.append(data)
    return dict(windows=result, boundary='Client-start windows; nested phases/SQL/locks overlap. Connection-return hold is an upper bound; no causal attribution or SLA pass inferred.')
