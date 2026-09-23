"""Isolated PostgreSQL service-query benchmark; creates/drops its own schema only."""
import os
os.environ['DATABASE_URL']='sqlite://'
import json,platform,sys,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine,text
from sqlalchemy.orm import Session
from app.models import uv_operations as m
from app.services.uv_operations import live

url='postgresql+psycopg://uvqa@127.0.0.1:55439/uv_ops_test'
schema='uvperf_'+uuid4().hex
admin=create_engine(url)
with admin.begin() as connection: connection.execute(text(f'CREATE SCHEMA "{schema}"'))
engine=create_engine(url,connect_args={'options':f'-csearch_path={schema}'},pool_size=50,max_overflow=0)
try:
    m.Base.metadata.create_all(engine,tables=[table for table in m.Base.metadata.sorted_tables if table.name.startswith('uv_ops_')])
    with Session(engine) as db:
        db.add(m.UvOpsSettings(id='huakang-a',factory_id='huakang-a',data_mode='synthetic'))
        db.add(m.UvOpsAgent(id='perf-agent',name='Synthetic capacity agent'))
        for i in range(20): db.add(m.UvOpsMachine(id=f'perf-machine-{i}',code=f'SYN-{i:02}',name='Synthetic machine'))
        db.flush()
        for i in range(20): db.add(m.UvOpsSourceBinding(id=f'perf-binding-{i}',agent_id='perf-agent',machine_id=f'perf-machine-{i}',source_id=f'perf-source-{i}',binding_version=1,adapter_type='simulator',capabilities={}))
        db.commit()
    with engine.begin() as connection:
        for start in range(0,100000,1000):
            connection.execute(m.UvOpsRun.__table__.insert(),[dict(id=f'perf-run-{i:06}',factory_id='huakang-a',machine_id=f'perf-machine-{i%20}',binding_id=f'perf-binding-{i%20}',native_job_id=f'job-{i}',native_identity=f'identity-{i}',last_observed_at='2026-09-23T00:01:00+00:00',started_at='2026-09-23T00:00:00+00:00',ended_at='2026-09-23T00:01:00+00:00',state='completed',match_evidence='Synthetic matched historical run') for i in range(start,start+1000)])
    def query(_):
        tick=time.perf_counter()
        with Session(engine) as db:
            data,coverage=live.workspace(db)
            assert len(data['machines'])==20 and data['collection_totals']['runs']==100000 and len(data['runs'])==100
        return (time.perf_counter()-tick)*1000
    with ThreadPoolExecutor(50) as pool: list(pool.map(query,range(50)))
    start=time.perf_counter()
    with ThreadPoolExecutor(50) as pool: values=list(pool.map(query,range(150)))
    ordered=sorted(values)
    result=dict(platform=platform.platform(),cpu=os.environ.get('PROCESSOR_IDENTIFIER'),database='PostgreSQL 16.15, loopback, separate disposable schema',network='localhost database service-query benchmark; excludes HTTP/browser rendering',machines=20,historical_runs=100000,concurrent_workers=50,measurements=len(values),window_seconds=round(time.perf_counter()-start,3),p50_ms=round(ordered[len(values)//2],2),p95_ms=round(ordered[int(len(values)*.95)],2),failure_rate=0,pool_size=50,schedule_days_loaded=0)
    Path('D:/RR/.tmp/uv-ops-20260923/query-benchmark.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
finally:
    engine.dispose()
    with admin.begin() as connection:connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()
