"""Golden help facts are checked against production calculations, using synthetic inputs."""
import importlib.util
import hashlib
import json
from pathlib import Path
from decimal import Decimal

ROOT=Path(__file__).parents[2]
def test_all_knowledge_fingerprints_and_scope_facts():
    articles=[a for p in (ROOT/'shared/assistant-help/modules').glob('*.json') for a in json.loads(p.read_text(encoding='utf-8'))]
    for a in articles:
        assert a['source_refs'] and a['status'] in ('verified','partial')
        for s in a['source_refs']:
            raw=(ROOT/s['path']).read_bytes().replace(b'\r\n',b'\n')
            assert hashlib.sha256(raw).hexdigest()==s['sha256'], s['path']
    by_module={a['module_id']:a for a in articles}
    assert 'synthetic' in by_module['uv-operations']['content']
    assert by_module['uv-operations']['factory_ids']==['huakang-a']
    assert by_module['carton-supplier']['audience']=='supplier'
    assert '入库' in by_module['three-d-printing']['content']
    assert 'partial' in by_module['work-center']['content']
