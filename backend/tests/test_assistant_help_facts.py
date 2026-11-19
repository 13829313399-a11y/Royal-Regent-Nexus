"""Golden help facts are checked against production calculations, using synthetic inputs."""
import importlib.util
import hashlib
import json
from pathlib import Path
from decimal import Decimal

ROOT=Path(__file__).parents[2]
spec=importlib.util.spec_from_file_location('assistant_calculation_reference',ROOT/'backend/app/services/injection_scheduling/calculations.py')
calc=importlib.util.module_from_spec(spec);spec.loader.exec_module(calc)


def test_injection_golden_cases_01_to_10():
    q=calc.quantities(dict(planned_shots=1000,opening_shots=100,adjustment_shots=50,target_shots_per_day=600,net_weight_g=20,price_per_shot=.1),reported_shots=200)
    assert [q[k] for k in ('completed_shots','remaining_shots','shots_per_hour','production_duration_hours','remaining_material_kg','remaining_processing_amount')]==[300,750,25,30,Decimal('15.15'),75]
    q=calc.quantities(dict(planned_shots=100),reported_shots=120)
    assert q['remaining_shots']==0 and q['overproduced_shots']==20
    assert calc.quantities({})['remaining_shots'] is None
    q=calc.quantities(dict(allocation_mode='CO_OUTPUT_UNITS',required_units=1001,effective_outputs_per_shot=3),good_units=201)
    assert q['remaining_units']==800 and q['remaining_shots']==267
    assert calc.co_output_shots([dict(remaining_units=200,outputs_per_shot=1),dict(remaining_units=150,outputs_per_shot=1)])==200
    assert calc.quantities(dict(allocation_mode='CO_OUTPUT_UNITS',required_units=100,effective_outputs_per_shot=0))['remaining_shots'] is None
    content=json.loads((ROOT/'shared/assistant-help/modules/injection-fields.json').read_text(encoding='utf-8'))[0]['content']
    for fact in ('计划+补数调整−期初−已上报','未知，不是零','向上取整','最大值','默认24','0.01','不是检修周期','未解释'):
        assert fact in content


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
