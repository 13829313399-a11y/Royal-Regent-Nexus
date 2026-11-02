"""Bounded source verification reuse; no TTL and no cross-read authorization."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest


def registry(monkeypatch,tmp_path):
    from app.services.assistant import help_registry as help
    source=tmp_path/'source.py';source.write_text('verified_symbol\nsecond_symbol\n',encoding='utf-8')
    directory=tmp_path/'help'/'modules';directory.mkdir(parents=True)
    rows=[]
    for index,symbol in enumerate(('verified_symbol','second_symbol')):
        rows.append(dict(id=f'help-{index}',module_id='portal',title='合成说明',kind='overview',audience='internal',route_names=['dashboard'],factory_ids=[],anchor_id='portal.overview',field_keys=[],summary='合成',content='只讲解已核对规则',steps=[],source_refs=[dict(path='source.py',symbol=symbol,sha256=hashlib.sha256(source.read_bytes().replace(b'\r\n',b'\n')).hexdigest())],knowledge_version='scope-test',verified_commit='synthetic',status='verified'))
    (directory/'test.json').write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
    monkeypatch.setattr(help,'ROOT',tmp_path);monkeypatch.setattr(help,'HELP_DIR',directory.parent)
    return help,source,SimpleNamespace(permissions=[])


def test_scoped_operation_reads_each_source_once_and_next_operation_detects_edits(monkeypatch,tmp_path):
    help,source,user=registry(monkeypatch,tmp_path)
    original=Path.read_bytes;reads=[]
    def counted(path):
        if path==source: reads.append(path)
        return original(path)
    monkeypatch.setattr(Path,'read_bytes',counted)
    with help.read_scope():
        assert help.get(user,'help-0').status=='verified'
        assert help.get(user,'help-1').status=='verified'
        ref=help.citation(help.get(user,'help-0'))
        assert help.references_current(user,[ref])
        source.write_text('changed source\n',encoding='utf-8')
        # A single bounded read is one source snapshot, not repeated disk IO.
        assert help.get(user,'help-0').status=='verified'
    assert len(reads)==1
    assert help.get(user,'help-0').status=='needs_review'
    assert not help.references_current(user,[ref])
    assert len(reads)==3, 'Every later read revalidates; there is no process cache'


def test_audience_is_checked_each_time_and_nested_scopes_end_with_the_operation(monkeypatch,tmp_path):
    from app.services.assistant.errors import AssistantError
    help,source,user=registry(monkeypatch,tmp_path)
    @help.scoped_read
    def operation():
        assert help.get(user,'help-0').status=='verified'
        with help.read_scope():
            with pytest.raises(AssistantError):
                help.get(SimpleNamespace(permissions=['carton_supplier:read']),'help-0')
        assert help.get(user,'help-1').status=='verified'
    operation()
    assert help._read_snapshot.get() is None
    source.unlink()
    assert help.get(user,'help-0').status=='needs_review'


def test_exception_cannot_leave_a_source_snapshot_for_later_guards(monkeypatch,tmp_path):
    help,source,user=registry(monkeypatch,tmp_path)
    @help.scoped_read
    def interrupted():
        help.get(user,'help-0')
        raise RuntimeError('synthetic interruption')
    with pytest.raises(RuntimeError): interrupted()
    assert help._read_snapshot.get() is None
    source.write_text('unverified content',encoding='utf-8')
    assert help.get(user,'help-0').status=='needs_review'
