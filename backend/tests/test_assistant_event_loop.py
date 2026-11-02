"""SQLite reader cleanup must run while a durable event waits to commit."""
import asyncio
from contextlib import asynccontextmanager
import json
import sqlite3
import threading
import time
from sqlalchemy import select
from test_assistant_api import env, session
from test_assistant_durable_runs import durable_env, post, wait_snapshot, frames


def test_durable_checkpoint_does_not_block_event_loop_reader_cleanup(durable_env):
    from app.services.assistant import durable, provider
    from app.models.assistant import AssistantProviderStep
    client, database, _, patch = durable_env
    released = threading.Event()
    delays = []
    readers = []
    calls = []
    original_record = durable.record
    async def get_loop():
        return asyncio.get_running_loop()
    loop = client.portal.call(get_loop)

    def observe_record(rid, lease, kind, data, *args):
        if kind == 'response.delta' and data.get('text') == 'AFTER_READER_RELEASE':
            reader = sqlite3.connect(database.engine.url.database,check_same_thread=False)
            readers.append(reader)
            reader.execute('BEGIN')
            reader.execute('SELECT count(*) FROM nexus_assistant_runs').fetchone()
            started = time.monotonic()
            def release():
                reader.rollback(); reader.close()
                delays.append(time.monotonic()-started)
                released.set()
            # Model the read transaction that a native request dependency
            # releases when the ASGI loop schedules response cleanup.
            loop.call_soon_threadsafe(lambda:loop.call_later(.08,release))
        return original_record(rid, lease, kind, data, *args)

    patch.setattr(durable, 'record', observe_record)

    @asynccontextmanager
    async def simulated(body):
        calls.append(1)
        async def chunks():
            def delta(text):
                return ('data: '+json.dumps(dict(id='loop-control',choices=[dict(delta=dict(content=text),finish_reason=None)]))+'\n\n').encode()
            yield delta('warm')
            yield delta('AFTER_READER_RELEASE')
            yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            yield b'data: {"choices":[],"usage":{"total_tokens":12}}\n\n'
            yield b'data: [DONE]\n\n'
        yield chunks()

    patch.setattr(provider, 'open_stream', simulated)
    try:
        sid = session(client)
        rid, _ = post(client,sid)
        snapshot = wait_snapshot(client,rid)
        assert snapshot['state']=='completed', dict(state=snapshot['state'],error=snapshot.get('error_code'),release_delays=delays)
        assert released.is_set() and len(delays)==1 and delays[0]<2
        assert 'warmAFTER_READER_RELEASE' in json.dumps(snapshot['items'])
        assert snapshot['usage']=={'total_tokens':12}
        events=frames(client.get('/api/assistant/runs/'+rid+'/events'))
        assert [e['data']['seq'] for e in events]==list(range(1,snapshot['event_seq']+1))
        assert sum(e['event']=='run.completed' for e in events)==1
        with database.SessionLocal() as db:
            steps=db.scalars(select(AssistantProviderStep).where(AssistantProviderStep.run_id==rid)).all()
            assert len(steps)==1 and steps[0].status=='completed'
        assert len(calls)==1
    finally:
        for reader in readers:
            try:reader.close()
            except sqlite3.ProgrammingError:pass
