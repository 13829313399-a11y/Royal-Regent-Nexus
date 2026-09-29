"""Isolated PostgreSQL service-query benchmark; creates/drops its own schema only."""
import os
os.environ['DATABASE_URL']='sqlite://'
import json,platform,sys,time,argparse
from datetime import datetime,timedelta,UTC
from threading import Barrier
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine,text
from sqlalchemy.orm import Session
from app.models import uv_operations as m
from app.services.uv_operations import live, common as c
from app.services.auth import AuthContext,AuthGrantContext

parser=argparse.ArgumentParser()
parser.add_argument('--output',required=True)
args=parser.parse_args()
url=os.environ.get('UV_OPS_TEST_POSTGRES_URL','postgresql+psycopg://uvqa@127.0.0.1:55439/uv_ops_test')
from sqlalchemy.engine import make_url
parsed=make_url(url)
assert parsed.host in {'localhost','127.0.0.1'} and parsed.database=='uv_ops_test'
codes=frozenset({'uv_ops:read','uv_ops:cost_read','uv_ops:payroll_read'})
grant=AuthGrantContext(role_id='synthetic',role_name='Synthetic',factory_id=m.FACTORY,department='production',permissions=codes)
user=AuthContext(id='benchmark',username='synthetic',display_name='Synthetic',roles=('test',),role_codes=('test',),permissions=codes,factory_scopes=(m.FACTORY,),department_scopes=('production',),grants=(grant,),active_permission_codes=codes)
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
    # Twenty physical fixtures, 20 x 30 x 10 distinct task/batch plans.
    with Session(engine) as db:
        product=c.add(db,m.UvOpsProduct,code='SYN-P',name='Synthetic product')
        demand=c.add(db,m.UvOpsDemand,code='SYN-D',product_id=product.id,product_snapshot=product.name,quantity=720000,allocated=720000,due_at='2026-10-01T00:00:00+00:00')
        templates=[]
        for index in range(20):
            fixture=c.add(db,m.UvOpsFixture,code=f'FIX-{index}',revision=1,slots=12,width_mm=100,height_mm=80)
            process=c.add(db,m.UvOpsProcessVersion,product_id=product.id,fixture_id=fixture.id,revision=index+1,name='Synthetic process',ink_family='synthetic',pieces_per_board=12,cycle_seconds=30,width_mm=100,height_mm=80)
            file=c.add(db,m.UvOpsFileVersion,process_version_id=process.id,role='production',name='synthetic.prn',sha256='0'*64,mime='application/octet-stream',size_bytes=1,content=b'x',confirmed_at=m.now(),first_article_evidence='Synthetic only')
            templates.append((process.id,file.id,fixture.id,c.record(process)))
        demand_id=demand.id
        db.commit()
    base=datetime(2026,9,1,tzinfo=UTC)
    tasks,batches,plans=[],[],[]
    for machine in range(20):
        process,file,fixture,snapshot=templates[machine]
        for day in range(30):
            for slot in range(10):
                key=f'schedule-{machine:02}-{day:02}-{slot:02}'
                start=base+timedelta(days=day,hours=slot)
                tasks.append(dict(id=key,code=key,demand_id=demand_id,process_version_id=process,file_version_id=file,quantity=120,status='planned',product_snapshot='Synthetic product',process_snapshot=snapshot,cost_price_snapshot={'currency':'CNY','basis':'piece','rate':'0.12'},payroll_policy_snapshot=None))
                batches.append(dict(id=key,task_id=key,quantity=120,remaining=120))
                plans.append(dict(id=key,task_id=key,batch_id=key,machine_id=f'perf-machine-{machine}',fixture_id=fixture,start_at=c.ts(start),end_at=c.ts(start+timedelta(minutes=5)),estimated_seconds=300))
    with engine.begin() as db:
        for model,values in [(m.UvOpsTask,tasks),(m.UvOpsBatch,batches),(m.UvOpsScheduleBlock,plans)]:
            for offset in range(0,len(values),500): db.execute(model.__table__.insert(),values[offset:offset+500])
        db.execute(text('ANALYZE'))
    def query(_):
        tick=time.perf_counter()
        with Session(engine) as db:
            result=live.response(db,user)
            data=result['data']
            assert len(data['machines'])==20 and data['collection_totals']['runs']==100000 and len(data['runs'])==100
            assert data['collection_totals']['schedule']==6000
        return (time.perf_counter()-tick)*1000
    def stats(values):
        ordered=sorted(values)
        return dict(p50_ms=round(ordered[len(values)//2],2),p95_ms=round(ordered[int(len(values)*.95)],2),max_ms=round(max(values),2),measurements=len(values))
    with ThreadPoolExecutor(50) as pool:
        barrier=Barrier(50)
        def cold(index):
            barrier.wait()
            return query(index)
        cold_values=list(pool.map(cold,range(50)))
        start=time.perf_counter()
        values=list(pool.map(query,range(150)))
    result=dict(platform=platform.platform(),cpu=os.environ.get('PROCESSOR_IDENTIFIER'),database='PostgreSQL 16.15, loopback, separate disposable schema',network='Service response including revision, Decimal serialization and per-user projection; excludes HTTP/authentication/browser',machines=20,historical_runs=100000,concurrent_workers=50,window_seconds=round(time.perf_counter()-start,3),failure_rate=0,pool_size=50,schedule_days_loaded=30,schedule_rows=6000,snapshot_policy='single-flight per committed revision; TTL 1 second; auth not cached',cold=stats(cold_values),steady=stats(values))
    Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
finally:
    engine.dispose()
    with admin.begin() as connection:connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()
