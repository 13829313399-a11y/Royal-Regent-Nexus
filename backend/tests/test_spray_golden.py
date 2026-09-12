import json
import sys
from decimal import Decimal as D
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.spray_calculations import arithmetic, complete_sets
from app.services.spray_production import calculate_wage, throughput, allocation

ROOT = Path(__file__).parent / 'fixtures' / 'spray'
GOLDEN = json.loads((ROOT / 'golden.json').read_text(encoding='utf-8'))
INPUTS = json.loads((ROOT / 'source_inputs.json').read_text(encoding='utf-8'))
SOURCE_CHECKS = [(case, check) for case in GOLDEN['cases'] if case['kind'].startswith('source_') for check in case['checks']]


@pytest.mark.parametrize('case,check', SOURCE_CHECKS, ids=[c['case_id']+':'+v['field'] for c,v in SOURCE_CHECKS])
def test_source_golden(case, check):
    if case['kind'] == 'source_cached_crosscheck':
        actual = sum(D(v) for v in case['inputs'].values())
    else:
        values = {k: D(v) for k,v in INPUTS[case['case_id']+':'+check['field']].items()}
        actual = arithmetic(check['formula'], values)
    assert abs(actual - D(check['expected_unrounded'])) <= D(check['tolerance'])


def test_structured_wage_throughput_and_tail_allocation():
    assert abs(calculate_wage('legacy_piece_normalized', {'rate':'.82','base_hours':'11','paid_hours':'12.5','rmb_per_hkd':'.88'}, D(560), D(11), D(7)) - D('592.9752066115702479')) < D('.000001')
    assert D(throughput(D(5000), D(1000), D('.12'), 2, D('.5'))['hours']) == D('5.5')
    assert complete_sets([('3000','1'),('2800','1')]) == 2800
    for total in (D('100'), D('-.05'), D('.01')):
        assert sum(D(x) for x in allocation(total, [D(1),D(1),D(1)])) == total


@pytest.mark.parametrize('formula', ['__import__("os")', 'x.y', 'A1**1000000', '[A1]', 'SUM(A1)', 'open("test")'])
def test_formula_does_not_execute_functions(formula):
    with pytest.raises(ValueError):
        arithmetic(formula, {'A1': D(1)})
