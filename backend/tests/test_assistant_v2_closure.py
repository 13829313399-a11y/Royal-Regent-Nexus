"""Remaining handoff risks: actual HTTP/process boundaries and filtered pagination."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from pathlib import Path
from types import SimpleNamespace
import json
import subprocess
import sys
import time
import pytest
from sqlalchemy import select
from test_assistant_api import env, session, payload
from test_assistant_v2 import migrate, ready


def eventually(check, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = check()
        if value: return value
        time.sleep(.025)
    pytest.fail('Expected bounded state transition did not occur')


@pytest.mark.parametrize('scenario,expected', [
    ('403','provider_access'), ('budget','provider_budget_exhausted'), ('429','provider_rate_limit'),
    ('503','provider_unavailable'), ('timeout','provider_timeout'), ('disconnect','provider_connection'),
    ('frame-budget','provider_budget_exhausted'), ('incomplete','provider_incomplete')])
def test_native_actual_http_failures_keep_partial_and_never_retry(monkeypatch, scenario, expected):
    from app.services.assistant import native_search
    from app.services.assistant.errors import AssistantError
    from app.schemas.assistant import SendMessage
    from pydantic import SecretStr
    calls = []
    partial = 'data: ' + json.dumps(dict(output=dict(choices=[dict(message=dict(content=[dict(text='已取得的部分正文')]),finish_reason=None)]))) + '\n\n'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            calls.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            status = int(scenario) if scenario.isdigit() else 403 if scenario == 'budget' else 200
            body = json.dumps({'code':'Arrearage' if scenario == 'budget' else 'SyntheticFailure'}).encode() if status != 200 else partial.encode()
            self.send_response(status)
            self.send_header('Content-Type','text/event-stream')
            self.send_header('Connection','close')
            if scenario == 'disconnect': self.send_header('Content-Length', str(len(body)+100))
            self.end_headers()
            if scenario == 'timeout': time.sleep(.3)
            try:
                self.wfile.write(body); self.wfile.flush()
                if scenario == 'disconnect': time.sleep(.04)
                if scenario == 'frame-budget': self.wfile.write(b'data: {"code":"Arrearage"}\n\n'); self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError): pass
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    for key, value in dict(assistant_search_endpoint=f'http://127.0.0.1:{server.server_port}/generation',
        assistant_qwen_api_key=SecretStr('synthetic-only'), assistant_upstream_idle_timeout_seconds=.08).items():
        monkeypatch.setattr(native_search.settings,key,value)
    received = []
    async def run():
        with pytest.raises(AssistantError) as error:
            async for item in native_search.stream([], SendMessage.model_validate(payload(protocol_version=2,web_search='on'))): received.append(item)
        assert error.value.detail['code'] == expected
    try: asyncio.run(run())
    finally: server.shutdown(); server.server_close(); thread.join()
    assert len(calls) == 1 and calls[0]['parameters']['search_options']['forced_search'] is True
    if scenario in ('disconnect','frame-budget','incomplete'):
        assert any(i.get('text') == '已取得的部分正文' for i in received)


def test_probe_default_is_offline_and_cannot_write_verified_profile(tmp_path):
    script = Path(__file__).parents[1]/'scripts/probe_assistant_search.py'
    target = tmp_path/'profile.json'
    result = subprocess.run([sys.executable,str(script),'--endpoint','http://127.0.0.1:1/unreachable','--output',str(target)],capture_output=True,text=True,timeout=15)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value['mode'] == 'offline' and value['verified'] is False and value['citation_resolved'] is True
    assert not target.exists()


def test_periodic_save_late_source_and_cancel_preserve_one_complete_evidence(env):
    client, dbm, calls, monkeypatch = env
    from app.services.assistant import native_search, search_capabilities
    from app.models.assistant import AssistantMessage
    release, closed = Event(), Event()
    monkeypatch.setattr(search_capabilities,'validate',lambda p:None)
    async def stream(*args):
        try:
            yield dict(kind='delta',channel='answer',text='先保存正文[ref_1]')
            await asyncio.to_thread(release.wait, 8)
            yield dict(kind='sources',items=[dict(index=1,url='https://example.test/late',title='Late source')])
            yield dict(kind='delta',channel='answer',text='；来源到达后的后续正文')
            await asyncio.sleep(8)
        finally: closed.set()
    monkeypatch.setattr(native_search,'stream',stream)
    sid=session(client)
    def saved():
        with dbm.SessionLocal() as db:
            row=db.scalar(select(AssistantMessage).where(AssistantMessage.session_id==sid,AssistantMessage.role=='assistant'))
            return (row.run_id,row.content_parts) if row else None
    def text_at_least(needle):
        value=saved()
        return value if value and needle in ''.join(p.get('text','') for p in value[1]) else None
    with ThreadPoolExecutor(max_workers=1) as pool:
        result=pool.submit(client.post,f'/api/assistant/sessions/{sid}/messages',json=payload(protocol_version=2,web_search='on'))
        try:
            rid, first=eventually(lambda:text_at_least('先保存正文'))
            assert not next(p for p in first if p['type']=='evidence')['sources']
            release.set()
            _, second=eventually(lambda:text_at_least('后续正文'))
            before=next(p for p in second if p['type']=='evidence')
            assert len(before['sources'])==1
            assert client.post(f'/api/assistant/runs/{rid}/cancel').status_code==200
            assert 'event: run.cancelled' in result.result(timeout=10).text
        finally: release.set()
    assert closed.wait(2) and len(calls)==0
    final=client.get(f'/api/assistant/runs/{rid}').json()
    assert final['state']=='cancelled'
    parts=final['items'][-1]['content_parts']
    assert sum(p['type']=='evidence' for p in parts)==1
    evidence=next(p for p in parts if p['type']=='evidence')
    assert evidence['sources']==before['sources'] and evidence['citations'][0]['resolution']=='resolved'
    assert all(a['status']!='running' for a in evidence['activities'])
    assert 'https://example.test/late' in client.get(f'/api/assistant/runs/{rid}/export').text


def test_process_timeout_delete_queue_and_recovery_release_capacity(env, tmp_path):
    client,dbm,_,monkeypatch=env
    from app.services.assistant import files
    from app.models.assistant import AssistantFile
    migrate(dbm); files.shutdown()
    monkeypatch.setattr(files.settings,'assistant_file_parse_concurrency',1)
    monkeypatch.setattr(files.settings,'assistant_file_parse_queue_limit',2)
    monkeypatch.setattr(files.settings,'assistant_file_parse_timeout_seconds',.3)
    children=[]
    def stuck(*args):
        child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        children.append(child); return child
    real=files.launch_parser
    monkeypatch.setattr(files,'launch_parser',stuck)
    sid=session(client)
    upload=lambda:client.post(f'/api/assistant/sessions/{sid}/files',files={'file':('synthetic.txt',b'data')})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:upload(), range(2)))
    ids=[r.json()['id'] for r in responses]
    assert upload().status_code==429
    assert all(ready(client,ident)['error_code']=='parse_timeout' for ident in ids)
    eventually(lambda:not files.JOBS)
    assert all(child.poll() is not None for child in children)
    monkeypatch.setattr(files.settings,'assistant_file_parse_timeout_seconds',30)
    ids=[upload().json()['id'],upload().json()['id']]
    eventually(lambda:len(children)==3)
    assert len([c for c in children if c.poll() is None])==1
    assert client.delete(f'/api/assistant/sessions/{sid}').status_code==200
    eventually(lambda:not files.JOBS)
    assert all(c.poll() is not None for c in children)
    with dbm.SessionLocal() as db:
        for ident in ids:
            row=db.get(AssistantFile,ident)
            if row:
                assert row.parse_status=='deleted'
                assert not files.path_for(row.storage_key).exists()
                assert not files.path_for(row.storage_key,True).exists()
    assert not list((Path(files.settings.assistant_storage_dir)/'documents').glob('*.parse-*.json'))
    monkeypatch.setattr(files,'launch_parser',real)
    sid=session(client)
    ident=upload().json()['id']; assert ready(client,ident)['parse_status']=='ready'
    with dbm.SessionLocal() as db:
        row=db.get(AssistantFile,ident); row.parse_status='parsing'; row.parse_owner='a'*32
        temporary=files.worker_path(row.storage_key,row.parse_owner); temporary.write_text('partial',encoding='utf-8'); db.commit()
    files.recover_jobs()
    assert ready(client,ident)['error_code']=='parse_interrupted' and not temporary.exists()


@pytest.mark.parametrize('failure', ['locked-output', 'database-unavailable'])
def test_cleanup_failures_always_release_slots_and_recover_status(env, monkeypatch, failure):
    client,dbm,_,_=env
    from app.services.assistant import files
    from app.models.assistant import AssistantFile
    migrate(dbm)
    sid=session(client)
    ident=client.post(f'/api/assistant/sessions/{sid}/files',files={'file':('cleanup.txt',b'synthetic')}).json()['id']
    assert ready(client,ident)['parse_status']=='ready'
    eventually(lambda:not files.JOBS)
    with dbm.SessionLocal() as db:
        row=db.get(AssistantFile,ident);row.parse_status='queued';key=row.storage_key;db.commit()
    files.JOBS[ident]=Event()
    original_session=dbm.SessionLocal
    original_unlink=Path.unlink
    def locked(path,*args,**kwargs):
        if '.parse-' in path.name: raise PermissionError('synthetic Windows file lock')
        return original_unlink(path,*args,**kwargs)
    def unavailable(*args,**kwargs): raise OSError('synthetic DB unavailable')
    def fail_launch(*args):
        monkeypatch.setattr(dbm,'SessionLocal',unavailable)
        raise OSError('synthetic process launch failure')
    if failure=='locked-output': monkeypatch.setattr(Path,'unlink',locked)
    else: monkeypatch.setattr(files,'launch_parser',fail_launch)
    files.parse_job(ident,'.txt',files.JOBS[ident])
    assert ident not in files.JOBS
    monkeypatch.setattr(dbm,'SessionLocal',original_session)
    monkeypatch.setattr(Path,'unlink',original_unlink)
    result=client.get(f'/api/assistant/files/{ident}').json()
    assert result['parse_status']==('ready' if failure=='locked-output' else 'failed')
    if failure=='database-unavailable': assert result['error_code']=='parse_interrupted'
    files.recover_jobs()
    assert not files.worker_path(key).exists()


def test_worker_exits_when_supervisor_pipe_closes(tmp_path):
    # Exercise the actual worker's parent-death path with a deliberately slow parser.
    from app.services.assistant import files
    import shutil
    worker=tmp_path/'document_worker.py'
    shutil.copy2(Path(files.__file__).with_name('document_worker.py'),worker)
    (tmp_path/'document_parser.py').write_text('import time\nclass DocumentParseError(Exception): pass\ndef extract(*a):\n time.sleep(30)\n return []\n',encoding='utf-8')
    source=tmp_path/'source';source.write_bytes(b'synthetic')
    child=subprocess.Popen([sys.executable,str(worker),str(source),str(tmp_path/'output'),'.txt','1','1000','30'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    try:
        time.sleep(.15); assert child.poll() is None
        child.stdin.close(); assert child.wait(timeout=3)==125
        assert not (tmp_path/'output').exists()
    finally:
        if child.poll() is None: child.kill();child.wait()
        child.stderr.close()


def test_filtered_pages_fill_with_late_matches_and_preserve_owner_epoch(env):
    client,dbm,_,_=env
    from app.models.assistant import AssistantSession,AssistantArtifact,AssistantArtifactVersion
    from app.models.auth import AuthUser
    from test_work_center_api import actor
    from app.services.assistant import service,artifacts
    migrate(dbm)
    sid=session(client);client.post(f'/api/assistant/sessions/{sid}/messages',json=payload())
    rid=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]['run_id']
    now=time.time()
    with dbm.SessionLocal() as db:
        user=actor('alice',department='production',permissions=()); epoch=service.epoch(user)
        for i in range(180):
            title='匹配目标' if i>=90 else '其他会话'
            db.add(AssistantSession(id=f'page-{i:03}',owner_user_id='alice' if i<160 else 'bob',employment_epoch=epoch if i<150 else epoch+1,create_request_id=f'page-{i}',title=title,revision=1,deletion_state='active',created_at=now,updated_at=now-i//3))
            refs=[] if i>=60 else [dict(kind='file',file_ref=dict(kind='document',id='deleted-file'))]
            db.add(AssistantArtifact(id=f'arte-{i:03}',owner_user_id='alice' if i<160 else 'bob',employment_epoch=epoch if i<150 else epoch+1,session_id=sid,source_run_id=rid,title=title,kind='note',current_revision=1,source_refs=refs,created_at=now,updated_at=now-i//3))
            db.flush(); db.add(AssistantArtifactVersion(artifact_id=f'arte-{i:03}',revision=1,content='正文',created_at=now))
        db.commit()
    for read in (lambda cur:service.sessions(user,cur,30,q='匹配目标'),lambda cur:artifacts.listing(user,'匹配目标',cur,30)):
        first=read(''); assert len(first['items'])==30 and first['next_cursor']
        second=read(first['next_cursor']); assert len(second['items'])==30 and second['next_cursor'] is None
        ids=[r['id'] for r in first['items']+second['items']]; assert len(set(ids))==60
    page=artifacts.listing(user,limit=30)
    assert len(page['items'])==30 and all(int(r['id'].split('-')[1])>=60 for r in page['items'])
    for cursor in ('nan:x','inf:x','1:','garbage'):
        with pytest.raises(Exception):artifacts.listing(user,cursor=cursor)


def test_printer_unknown_future_missing_and_network_outage_reuse_real_dto(env):
    from datetime import datetime,timezone,timedelta
    from test_work_center_api import actor
    from app.models.three_d_printing import ThreeDPrintingPrinter
    from app.services import three_d_printing as printers
    from app.services.assistant import business
    _,dbm,_,monkeypatch=env
    now=printers.business_now().replace(microsecond=0); stamp=lambda t:t.strftime('%Y-%m-%d %H:%M:%S')
    monkeypatch.setattr(printers,'business_now',lambda:now)
    user=actor('alice',department='production',permissions=('three_d_printing:read',))
    with dbm.SessionLocal() as db:
        for i,age in enumerate([0,120,-120,None,0]):
            db.add(ThreeDPrintingPrinter(id=f'closure-{i}',factory_id='huakang-a',machine_no=200+i,name='Synthetic',state='RUNNING',connected=True,last_seen_at=stamp(now-timedelta(seconds=age)) if age is not None else None,created_at=stamp(now),updated_at=stamp(now),status_payload_json=json.dumps({'connector':{'observation_only':True}}) if i==4 else '{}'))
        db.commit()
    for network_status in ['healthy','degraded','unknown']:
        monkeypatch.setattr(printers,'network_health_snapshot',lambda db:dict(configured=True,status=network_status,observed_at=None))
        result,source,_=business.query(user,'get_printer_status',{'factory_id':'huakang-a'},'probe')
        with dbm.SessionLocal() as db:
            expected={f'closure-{i}':printers.printer_out(db.get(ThreeDPrintingPrinter,f'closure-{i}'),network_stale=network_status!='healthy') for i in range(5)}
        actual={p['id']:p for p in result['items'] if p['id'] in expected}
        assert actual==expected and all(actual[f'closure-{i}']['status_stale'] for i in (1,2,3))
        assert actual['closure-0']['status_stale']==(network_status!='healthy')
        assert actual['closure-4']['status_stale'] is False
        assert result['network_health']['status']==network_status and 'physical_state' in source['unknown_fields']
