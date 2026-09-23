"""Synthetic API fixtures for the explicitly isolated preview server only."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from datetime import datetime,timedelta,UTC
from secrets import token_urlsafe
from uuid import uuid4
import httpx
from test_uv_ops import setup_task,post,read,confirm,payload

client=httpx.Client(base_url='http://127.0.0.1:8019',timeout=90)
health=client.get('/health').json()
assert health['data_mode']=='synthetic'
login=client.post('/api/auth/login',json=dict(username='uvqa',password='Uv-QA-only-2026!'))
assert login.status_code==200,login.text
assert not read(client,'machines'),'Preview already seeded; refusing duplicate fixtures'
tasks=[]
for index,(name,product,quantity) in enumerate([('平板 UV · 一号机','透明铭牌 · 银白印面',120),('平板 UV · 二号机','展示底座 · 彩色标识',960),('小幅 UV · 三号机','包装饰片 · 图案印面',360)],start=1):
    data=setup_task(client,quantity=quantity)
    machine=data['machine']
    response=client.patch('/api/uv-operations/machines/'+machine['id'],json=payload(expected_version=machine['version'],code='UV-0'+str(index),name=name,model='合成验收设备',width_mm='2500',height_mm='1300',ink_family='synthetic-hard',capability_evidence='合成验收尺寸；不代表现场设备'))
    assert response.status_code==200,response.text
    machine=response.json()['data']
    if index==1:
        data['batch']=confirm(client,data)['batch']
    agent=post(client,'agents',name='合成采集端 '+str(index))
    token=token_urlsafe(48)
    enroll=client.post('/api/internal/uv-agent/enroll',json=dict(pairing_code=agent['pairing_code'],enrollment_id=uuid4().hex,token=token))
    assert enroll.status_code==200
    source=post(client,'sources',agent_id=agent['agent']['id'],machine_id=machine['id'],source_id='sim-'+str(index),adapter_type='simulator')
    headers={'Authorization':'Bearer '+token}
    now=datetime.now(UTC)
    event=dict(event_id=uuid4().hex,stream_id=uuid4().hex,sequence=1,machine_id=machine['id'],source_id=source['source_id'],binding_version=source['binding_version'],kind='job_start',observed_at=now.isoformat(),adapter_type='simulator',adapter_version='1.0.1',source_identity=dict(generation='synthetic-session',job_identity=uuid4().hex),evidence=dict(synthetic=True),payload=dict(native_job_id='QA-JOB-'+str(index).zfill(3),count='0',count_unit='board',counter_mode='cumulative',ink_total_ml=None,work_state='running'))
    response=client.post('/api/internal/uv-agent/events/batch',headers=headers,json=dict(schema_version=1,batch_id=uuid4().hex,events=[event]))
    assert response.json()['results'][0]['status']=='persisted',response.text
    client.post('/api/internal/uv-agent/heartbeat',headers=headers,json=dict(agent_version='synthetic-qa',queue_count=0,oldest_age_seconds=0,collector_health='ready'))
    if index>1:
        post(client,'schedule/commit',blocks=[dict(task_id=data['task']['id'],machine_id=machine['id'],task_version=data['task']['version'],machine_version=machine['version'],block_version=0,start_at=(now+timedelta(hours=1)).isoformat(),end_at=(now+timedelta(hours=3)).isoformat(),fixed=index==3)])
    tasks.append(data)
sku=post(client,'ink/skus',code='INK-HARD-C-01',supplier='合成供应商',model='演示硬墨',ink_family='synthetic-hard',color='青色 C',capacity_ml='1000')
post(client,'ink/movements',sku_id=sku['id'],location='主仓',lot='SYN-202609',kind='receipt',quantity_ml='3000',cost_value='600',currency='CNY',business_date='2026-09-23',evidence='隔离环境合成入库')
print('Synthetic API fixture ready: 3 machines, 3 tasks, 3 agent runs, 2 schedule blocks, 1 ink SKU. No production data.')
