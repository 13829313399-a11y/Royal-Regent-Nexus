"""Release evidence must distinguish partial checks from production readiness."""
import importlib.util
from pathlib import Path
import sys
import pytest
from cutting_postgres_safety import dedicated_postgres_url

sys.path.insert(0, str(Path(__file__).parents[1]/'scripts'))
spec = importlib.util.spec_from_file_location('p5c_runner', Path(__file__).parents[1]/'scripts/verify_cutting_p5c.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize('url', ['postgresql://host/business', 'postgresql://host/business_cutting_test',
    'postgresql://host/cutting_testproduction', 'postgresql://host/', 'sqlite:///cutting_test',
    'postgresql://host/cutting_test?dbname=business', 'postgresql://host/cutting_test?database=business',
    'postgresql://host/cutting_test?service=business'])
def test_direct_fixtures_reject_names_that_are_not_dedicated(url):
    with pytest.raises(ValueError):
        dedicated_postgres_url(url)
    with pytest.raises(ValueError):
        runner.validate_postgres(url)


@pytest.mark.parametrize('name', ['cutting_test', 'cutting_test_release'])
def test_direct_fixtures_accept_only_explicit_test_database_names(name):
    assert dedicated_postgres_url('postgresql://localhost/'+name).database == name


@pytest.mark.parametrize('url', ['sqlite:///business.db', 'postgresql://secret:private@host/business',
                              'postgresql://host/not_cutting_test', 'invalid'])
def test_rejects_non_dedicated_databases_without_echoing_secrets(url):
    with pytest.raises(ValueError) as error:
        runner.validate_postgres(url)
    assert 'private' not in str(error.value) and 'secret' not in str(error.value)


def test_postgres_is_explicit_and_scoped():
    assert not runner.validate_postgres('')
    assert runner.validate_postgres('postgresql://localhost/cutting_test_release')


@pytest.mark.parametrize('change', ['failure', 'missing_step', 'source_changed', 'required_pg_missing', 'pg_skipped'])
def test_incomplete_runs_fail_closed(change):
    steps = [{'step':'one','exit_code': 1 if change == 'failure' else 0}]
    suites = {'one': {'tests':1,'failed': 0, 'skipped': [{'test': 'pg'}] if change == 'pg_skipped' else []}}
    result = runner.outcome(steps, 2 if change == 'missing_step' else 1, suites,
                            change != 'source_changed', True, change != 'required_pg_missing')
    assert result['automated_status'] == 'failed' and not result['release_ready']


def test_local_pass_preserves_skips_and_never_becomes_release_acceptance():
    result = runner.outcome([{'step':'one','exit_code': 0}], 1, {'one':{'tests':2,'failed': 0, 'skipped': [{'test': 'test_case[postgresql]'}]}}, True, False, False)
    assert result['automated_status'] == 'passed' and result['skipped']
    assert result['postgresql'] == 'not_accepted' and not result['release_ready']


def test_unrelated_skips_cannot_pass_sqlite_acceptance():
    result = runner.outcome([{'step':'capacity','exit_code':0}], 1,
        {'capacity':{'tests':1,'failed':0,'skipped':[{'test':'test_multi_order'}]}}, True, False, False)
    assert result['automated_status'] == 'failed'


def test_group_with_only_postgres_skips_is_missing_sqlite_evidence():
    result = runner.outcome([{'step':'concurrency','exit_code':0}], 1,
        {'concurrency':{'tests':1,'failed':0,'skipped':[{'test':'test_case[postgresql]'}]}}, True, False, False)
    assert result['automated_status'] == 'failed'


@pytest.mark.parametrize('suites', [{}, {'wrong':{'tests':1,'failed':0,'skipped':[]}},
                                    {'one':{'tests':0,'failed':0,'skipped':[]}}])
def test_missing_mismatched_or_empty_evidence_cannot_pass(suites):
    result = runner.outcome([{'step':'one','exit_code':0}], 1, suites, True, False, False)
    assert result['automated_status'] == 'failed'


def test_missing_and_malformed_junit_are_reported(tmp_path):
    path = tmp_path/'evidence.xml'
    assert runner.read_suite(path)['failed'] == 1
    path.write_text('<testsuites>broken')
    assert runner.read_suite(path)['failed'] == 1


def test_connection_is_redacted_before_archiving(tmp_path):
    connection = 'postgresql://user:private-secret@host/cutting_test_release'
    path = tmp_path/'step.log'
    path.write_text(connection+' password=private-secret', encoding='utf-8')
    runner.redact_connection_logs(tmp_path, connection)
    assert 'private-secret' not in path.read_text() and connection not in path.read_text()


def test_xml_escaped_password_is_redacted_without_breaking_junit(tmp_path):
    path = tmp_path/'step.xml'
    path.write_text('<testsuites><testsuite><testcase name="one"><failure message="a&amp;b">a&amp;b</failure></testcase></testsuite></testsuites>', encoding='utf-8')
    runner.redact_connection_logs(tmp_path, 'postgresql://user:a%26b@host/cutting_test_release')
    assert 'a&amp;b' not in path.read_text()
    assert runner.read_suite(path)['tests'] == 1 and runner.read_suite(path)['failed'] == 1


def test_sqlite_only_ignores_inherited_connection_and_preserves_incomplete_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('CUTTING_TEST_POSTGRES_URL', 'postgresql://private:secret@host/business')
    monkeypatch.setenv('PYTEST_ADDOPTS', '-k postgres')
    monkeypatch.setattr(sys, 'argv', ['verify_cutting_p5c.py', '--sqlite-only'])
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    monkeypatch.setattr(runner, 'source_state', lambda: {})
    captured = {}
    def execute(steps, output, env):
        captured.update(env)
        assert any(name == 'http-capacity' and 'tests/test_cutting_http_capacity.py' in command
                   for name, command, _ in steps)
        assert any(name == 'http-capacity' and all('tests/'+file in command for file in
                   ['test_cutting_http_process.py', 'test_cutting_lock_phases.py',
                    'test_cutting_production_mix.py']) for name, command, _ in steps)
        return []
    monkeypatch.setattr(runner, 'execute_steps', execute)
    assert runner.main() == 1  # No test evidence must never become a pass.
    assert captured['CUTTING_TEST_POSTGRES_URL'] == ''
    assert captured['DATABASE_URL'] == 'sqlite://'
    assert captured['PYTEST_ADDOPTS'] == ''
    assert captured['CUTTING_SOAK_SECONDS'] == '3'
    assert captured['CUTTING_SOAK_WORKLOAD'] == 'paced'
    assert captured['CUTTING_FINANCE_SOAK_WORKERS'] == '5'
    assert captured['CUTTING_FINANCE_SOAK_FINANCE_CHAINS'] == '2'
    assert captured['CUTTING_FINANCE_SOAK_SECONDS'] == '3'
    for path in tmp_path.rglob('*.json'):
        assert 'private:secret' not in path.read_text(encoding='utf-8')


def test_sqlite_only_cannot_request_postgres(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['verify_cutting_p5c.py', '--sqlite-only', '--require-postgres'])
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2


def test_expanded_financial_runner_pins_synthetic_scope_and_cannot_pass_without_evidence(tmp_path,monkeypatch):
    import verify_cutting_http_soak as soak
    monkeypatch.setattr(sys,'argv',['verify_cutting_http_soak.py','--profile','500','--expanded-finance','--seconds','600'])
    monkeypatch.setenv('DATABASE_URL','sqlite:///original-business.db')
    monkeypatch.setenv('CUTTING_FINANCE_SOAK_CHAINS','9999')
    monkeypatch.setenv('PYTEST_ADDOPTS','-k nothing')
    monkeypatch.setattr(soak,'ROOT',tmp_path)
    monkeypatch.setattr(soak,'source_state',lambda:{})
    captured = {}
    def execute(steps,output,env,**kwargs):
        captured.update(env)
        assert 'tests/test_cutting_financial_soak.py::test_expanded_financial_mixed_http' in steps[0][1]
        return []
    monkeypatch.setattr(soak,'execute_steps',execute)
    assert soak.main()==1
    assert captured['DATABASE_URL']=='sqlite://' and captured['CUTTING_TEST_POSTGRES_URL']==''
    assert captured['PYTEST_ADDOPTS']==''
    assert {k:captured['CUTTING_FINANCE_SOAK_'+k] for k in ('ORDERS','CHAINS','FINANCE_CHAINS','WORKERS','SECONDS')} == dict(
        ORDERS='500',CHAINS='100',FINANCE_CHAINS='20',WORKERS='10',SECONDS='600')
