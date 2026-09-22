"""Opt-in synthetic volume benchmark, isolated by the standard fixture.

Run SPRAY_OPS_RUN_PERFORMANCE=1; this is neither PostgreSQL nor field acceptance.
"""
import json
import os
from datetime import datetime, timedelta, UTC
from time import perf_counter

import pytest
from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.models import spray_ops as m
from test_spray_ops import client, payload


@pytest.mark.skipif(os.environ.get('SPRAY_OPS_RUN_PERFORMANCE') != '1', reason='Explicit isolated performance run only')
def test_100_resources_2000_tasks_10000_reports(client):
    f, stamp = 'huaxing', '2026-09-01T00:00:00+00:00'
    def insert_all(db, model, values):
        db.execute(insert(model), [dict(factory_id=f, **value) for value in values])
    with Session(client.spray_engine) as db:
        insert_all(db, m.SprayOpsResource, [dict(id=f'res{i}', code=f'M{i:03d}', name=f'测试资源{i}', kind='manual') for i in range(100)])
        insert_all(db, m.SprayOpsCapability, [dict(resource_id=f'res{i}', capability='coat', hourly_capacity=1000, evidence='合成基准') for i in range(100)])
        insert_all(db, m.SprayOpsCalendar, [dict(resource_id=f'res{i}', start_at='2026-09-01T00:00:00+00:00', end_at='2026-10-10T00:00:00+00:00', kind='available') for i in range(100)])
        insert_all(db, m.SprayOpsRoute, [dict(id='route', code='BENCH', label='基准路线', revision=1, status='confirmed')])
        insert_all(db, m.SprayOpsStep, [dict(id='step', route_id='route', code='S1', name='喷色', capability='coat', input_unit='件', output_unit='件', prep_required=False)])
        insert_all(db, m.SprayOpsDemand, [dict(id=f'd{i}', document_no=f'D{i:05d}', counterparty='合成客户', business_date='2026-09-01', status='confirmed') for i in range(2200)])
        insert_all(db, m.SprayOpsDemandLine, [dict(id=f'l{i}', demand_id=f'd{i}', item_no=f'{i:05d}', part='左', color='灰', quantity=100, unit='件', due_date='2026-10-06', route_id='route') for i in range(2200)])
        insert_all(db, m.SprayOpsBatch, [dict(id=f'b{i}', document_no=f'B{i:05d}', line_id=f'l{i}', item_no=f'{i:05d}', part='左', quantity=100, accepted=100, unit='件', business_date='2026-09-01') for i in range(2200)])
        insert_all(db, m.SprayOpsStock, [dict(id=f's{i}', batch_id=f'b{i}', line_id=f'l{i}', state='white', quantity=0 if i<1000 else 100, reserved=100 if 1000<=i<2000 else 0, unit='件', ready_at=stamp) for i in range(2200)])
        task_values = []
        for i in range(2000):
            at = datetime(2026,9,2 if i<1000 else 22,tzinfo=UTC)+timedelta(minutes=(i%1000//100)*6)
            task_values.append(dict(id=f't{i}', step_id='step', resource_id=f'res{i%100}', start_at=at.isoformat(), end_at=(at+timedelta(minutes=6)).isoformat(), quantity=100, reported=100 if i<1000 else 0, status='completed' if i<1000 else 'planned'))
        insert_all(db, m.SprayOpsTask, task_values)
        insert_all(db, m.SprayOpsTaskAllocation, [dict(id=f'ta{i}', task_id=f't{i}', stock_id=f's{i}', line_id=f'l{i}', quantity=100, consumed=100 if i<1000 else 0) for i in range(2000)])
        insert_all(db, m.SprayOpsReport, [dict(id=f'r{i}', document_no=f'R{i:05d}', business_date='2026-09-02', shift='基准白班', status='confirmed') for i in range(10000)])
        insert_all(db, m.SprayOpsReportRow, [dict(id=f'rr{i}', report_id=f'r{i}', task_id=f't{i//10}', processed=10, good=10, hold=0, scrap=0, normal=10, overtime=0) for i in range(10000)])
        insert_all(db, m.SprayOpsReportAllocation, [dict(row_id=f'rr{i}', task_allocation_id=f'ta{i//10}', processed=10, good=10, hold=0, scrap=0, normal=10, overtime=0) for i in range(10000)])
        db.commit()
    timings = {}
    for name in ['reports', 'tasks', 'plan']:
        measured = []
        for sample in range(21):
            at = perf_counter()
            if name == 'plan':
                response = client.post('/api/spray-operations/scenarios/preview', json=payload(start_at='2026-09-22T00:00:00Z', end_at='2026-10-06T00:00:00Z'))
            else:
                response = client.get('/api/spray-operations/'+name, params=dict(factory_id=f, page_size=50))
            elapsed = (perf_counter()-at)*1000
            assert response.status_code == 200, response.text
            if name == 'plan':
                assert len(response.json()['data']['snapshot']['tasks']) == 200
            if sample:
                measured.append(elapsed)
        timings[name] = round(sorted(measured)[18], 2)
    print('SPRAY_BENCHMARK_P95_MS='+json.dumps(timings))
    assert timings['reports'] <= 800 and timings['tasks'] <= 800
    assert timings['plan'] <= 1500
