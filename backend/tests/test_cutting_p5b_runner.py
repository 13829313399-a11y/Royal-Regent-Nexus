"""Acceptance reporting must fail closed without invoking any real processes."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('p5b_runner', Path(__file__).parents[1]/'scripts/verify_cutting_p5b.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_failed_step_prevents_later_checks(tmp_path):
    calls = []
    def fail(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=7)
    result = runner.execute_steps([('one',['first'],tmp_path),('two',['must-not-run'],tmp_path)],tmp_path,{},fail)
    assert calls == [['first']] and result[0]['exit_code']==7 and len(result)==1


def test_missing_command_is_recorded_as_failure(tmp_path):
    def missing(*args,**kwargs):
        raise FileNotFoundError('missing test runtime')
    assert runner.execute_steps([('one',['missing'],tmp_path)],tmp_path,{},missing)[0]['exit_code']==-1
    assert 'missing test runtime' in (tmp_path/'one.log').read_text()


def test_interruption_is_recorded_and_stops_remaining_steps(tmp_path):
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt()
    result = runner.execute_steps([('one',['first'],tmp_path),('two',['second'],tmp_path)],tmp_path,{},interrupt)
    assert len(result)==1 and result[0]['exit_code']==130


def test_skips_and_failures_never_become_passes(tmp_path):
    xml = tmp_path/'results.xml'
    xml.write_text('<testsuites><testsuite><testcase name="ok"/><testcase name="pg"><skipped message="no dedicated database"/></testcase><testcase name="bad"><failure/></testcase></testsuite></testsuites>')
    result = runner.junit_summary(xml)
    assert result['tests']==3 and result['failed']==1 and len(result['skipped'])==1
    assert result['skipped'][0]['reason']=='no dedicated database'
