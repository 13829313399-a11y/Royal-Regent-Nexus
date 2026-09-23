"""Synthetic 72-hour capacity model; not a 72-hour wall-clock/site soak test."""
import argparse,json,platform,time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uv_agent.outbox import Outbox

parser=argparse.ArgumentParser()
parser.add_argument('--directory',required=True)
args=parser.parse_args()
base=Path(args.directory).resolve()
base.mkdir(parents=True,exist_ok=True)
path=base/'capacity.sqlite3'
if path.exists():raise SystemExit('Refusing to overwrite existing queue')
count=20*72*60*3
box=Outbox(path,min_free_bytes=100*1024*1024)
event=dict(machine_id='synthetic-machine',source_id='synthetic-source',binding_version=1,kind='job_complete',observed_at='2026-09-23T00:00:00+00:00',adapter_type='simulator',adapter_version='1.0.0',source_identity={'generation':'synthetic'},evidence={'synthetic':True,'note':'72-hour capacity model only'},payload={'native_job_id':'synthetic','count':'1','count_unit':'board','counter_mode':'delta','ink_total_ml':None,'work_state':'idle'})
latencies=[]
start=time.perf_counter()
for index in range(0,count,1000):
    tick=time.perf_counter()
    box.append('synthetic',[event]*min(1000,count-index),{'offset':min(count,index+1000)})
    latencies.append((time.perf_counter()-tick)*1000)
enqueue=time.perf_counter()-start
box.close()
size=path.stat().st_size
box=Outbox(path,min_free_bytes=0)
assert box.diagnostics()['queue_count']==count and box.cursor('synthetic')['offset']==count
start=time.perf_counter();drained=0
while rows:=box.pending(1000):
    box.acknowledge([dict(event_id=row['event_id'],status='persisted') for row in rows])
    drained+=len(rows)
drain=time.perf_counter()-start
assert drained==count and box.diagnostics()['queue_count']==0
result=dict(platform=platform.platform(),python=platform.python_version(),sqlite_version=box.diagnostics()['sqlite_version'],mode='accelerated_capacity_model_not_wall_clock_soak',machines=20,hours=72,jobs_per_machine_minute=1,key_events_per_job=3,event_count=count,database_bytes=size,enqueue_seconds=round(enqueue,3),enqueue_batch_p50_ms=round(sorted(latencies)[len(latencies)//2],3),enqueue_batch_p95_ms=round(sorted(latencies)[int(len(latencies)*.95)],3),local_ack_events_per_second=round(count/drain,2),restored_after_restart=True,remaining=0,failure_rate=0,network='none; local disk ACK benchmark, not server recovery throughput')
box.close()
(base/'capacity-evidence.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
