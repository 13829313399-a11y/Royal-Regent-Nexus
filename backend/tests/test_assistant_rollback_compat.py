"""The rollback reader must preserve legacy behavior and fail closed for V3."""
import json
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.orm import Session
from app.services.assistant import rollback_compat
from test_assistant_api import env,session
from test_assistant_durable_runs import durable_env,post,wait_snapshot


@pytest.mark.parametrize('payload',[{}, {'protocol_version':1},{'protocol_version':2}])
def test_legacy_requests_need_no_new_table_or_connection(payload):
    assert rollback_compat.source_refs(None,SimpleNamespace(id='legacy',request_input=payload))==[]


@pytest.mark.parametrize('payload',[None,{'protocol_version':True},{'protocol_version':0},{'protocol_version':'3'},{'protocol_version':4}])
def test_unknown_or_malformed_run_protocol_is_not_assumed_to_be_legacy(payload):
    assert rollback_compat.source_refs(None,SimpleNamespace(id='unknown',request_input=payload)) is None


@pytest.mark.parametrize('raw',[None,'not json','{}','"[]"','[null]',
    '[{"source_id":"x","kind":"unknown"}]','[{"source_id":"","kind":"web"}]'])
def test_missing_or_unrecognized_dependency_data_fails_closed(raw):
    assert rollback_compat.decode_refs(raw) is None


def test_sqlite_execution_row_is_read_without_new_orm_and_does_not_mutate_dependencies():
    engine=create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE nexus_assistant_executions (run_id TEXT PRIMARY KEY, source_refs JSON)'))
        conn.execute(text('INSERT INTO nexus_assistant_executions VALUES (:rid,:refs)'),{'rid':'saved','refs':json.dumps([{'source_id':'source','kind':'web','title':'retained'}])})
    run=SimpleNamespace(id='saved',request_input={'protocol_version':3})
    with Session(engine) as db:
        value=rollback_compat.source_refs(db,run)
        assert value==[{'source_id':'source','kind':'web','title':'retained'}]
        value[0]['title']='local mutation'
        assert rollback_compat.source_refs(db,run)[0]['title']=='retained'
        assert rollback_compat.source_refs(db,SimpleNamespace(id='absent',request_input={'protocol_version':3})) is None
    native=[{'source_id':'source','kind':'web'}]
    projected=rollback_compat.decode_refs(native);projected[0]['source_id']='changed'
    assert native[0]['source_id']=='source'
    engine.dispose()


@pytest.mark.parametrize('ddl',[None,'CREATE TABLE nexus_assistant_executions (run_id TEXT PRIMARY KEY)'])
def test_missing_table_or_column_keeps_read_transaction_usable(ddl):
    engine=create_engine('sqlite://')
    with engine.begin() as conn:
        if ddl:conn.execute(text(ddl))
    with Session(engine) as db:
        assert rollback_compat.source_refs(db,SimpleNamespace(id='saved',request_input={'protocol_version':3})) is None
        assert db.scalar(text('SELECT 1'))==1
    engine.dispose()


def test_current_history_and_export_hide_v3_when_execution_dependency_row_is_missing(durable_env):
    from app.models.assistant import AssistantExecution
    client,dbm,_,_=durable_env
    rid,_=post(client,session(client))
    original=wait_snapshot(client,rid)
    assert not any(m.get('unavailable') for m in original['items'])
    with dbm.SessionLocal() as db:
        db.delete(db.get(AssistantExecution,rid));db.commit()
    hidden=client.get('/api/assistant/runs/'+rid)
    assert hidden.status_code==200 and all(m.get('unavailable') for m in hidden.json()['items'])
    assert '自由回答' not in hidden.text
    assert client.get('/api/assistant/runs/'+rid+'/export').status_code==410
