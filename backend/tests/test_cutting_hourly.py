"""Duration/coverage/failure fences for the isolated hour-scale runner."""
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_cutting_hourly as runner


@pytest.mark.parametrize('seconds',[-1,0,9,3601,True])
def test_invalid_duration_rejected(seconds):
    with pytest.raises(ValueError):runner.validate_duration(seconds)


def successful_cycle(url,database,cycle,**options):
    assert options['concentrated_exports'] is True and options['chains']==100
    assert 10 <= options['minimum_seconds'] <= 60
    cycle.update(status='passed',finance=dict(same_balance_protected=True),
        materials=dict(receipt_race_protected=True,return_correction_preserved=True),
        period=dict(locked_write_rejected=True,historical_snapshot_unchanged=True),reader_cycles=[1,1,1])


def test_short_probe_never_becomes_hour_acceptance_and_uses_fresh_lines():
    ticks=iter([0,0,6,6,12,12,12]);report={}
    runner.run_cycles('owned',Path('synthetic'),10,report,invoke=successful_cycle,clock=lambda:next(ticks))
    assert not report['hour_duration_achieved']
    assert [c['line_id'] for c in report['cycles']]==['http-capacity-20','http-capacity-21']


def test_partial_failure_is_retained_and_never_silently_retried():
    report={};checkpoints=[]
    def fail(*args,**kwargs):raise RuntimeError('injected failure')
    with pytest.raises(RuntimeError,match='injected'):
        runner.run_cycles('owned',Path('synthetic'),3600,report,invoke=fail,clock=lambda:0,
            checkpoint=lambda:checkpoints.append(len(report['cycles'])))
    assert report['cycles'][0]['status']=='failed' and checkpoints==[1]
    assert 'hour_duration_achieved' not in report


def test_missing_transition_coverage_cannot_pass():
    def missing(*args,**kwargs):
        successful_cycle(*args,**kwargs);args[2]['period']['locked_write_rejected']=False
    with pytest.raises(AssertionError):
        runner.run_cycles('owned',Path('synthetic'),10,{},invoke=missing,clock=lambda:0)


def test_exhausted_fresh_lines_fail_closed():
    report={}
    with pytest.raises(ValueError,match='fresh-line'):
        runner.run_cycles('owned',Path('synthetic'),3600,report,invoke=successful_cycle,clock=lambda:0)
    assert len({c['line_id'] for c in report['cycles']})==80
