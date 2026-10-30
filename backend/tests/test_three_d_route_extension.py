"""Run the Windows route handoff with an isolated, stateful Tailscale stub."""
import csv
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows PowerShell field handoff')
SOURCE=Path(__file__).resolve().parents[2]/'deploy/three-d-printing/network/extend-printer-routes.ps1'
ORIGINAL=['10.20.0.0/16','10.33.30.101/32','fd7a:115c:a1e0::/48']
ADDED=['10.33.30.106/32','10.33.30.107/32']


@pytest.fixture
def route_case(tmp_path):
    root=tmp_path/'现场 路由工具';root.mkdir()
    inventory=root/'printers.csv'
    with inventory.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['machine_no','ip']);w.writerows([(6,'10.33.30.106'),(7,'10.33.30.107')])
    state=root/'state.json'
    state.write_text(json.dumps({'routes':ORIGINAL,'calls':[],'reads':0,'gateway':'100.64.0.7','running':True}),encoding='utf-8')
    fake=root/'fake-tailscale.ps1'
    fake.write_text('''param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
$state=Get-Content -LiteralPath $env:RR_ROUTE_TEST_STATE -Raw | ConvertFrom-Json
$state.calls=@($state.calls)+@(($Arguments -join ' '))
$global:LASTEXITCODE=0
$reply=''
if ($Arguments[0] -eq 'status') {
 $reply=@{BackendState=if($state.running){'Running'}else{'NeedsLogin'};TailscaleIPs=@($state.gateway)} | ConvertTo-Json -Compress
} elseif ($Arguments[0] -eq 'debug') {
 $state.reads++
 if ($state.race -and $state.reads -eq 2) { $state.routes=@($state.routes)+@('10.50.0.0/16') }
 $reply=@{AdvertiseRoutes=@($state.routes)} | ConvertTo-Json -Compress
} elseif ($Arguments[0] -eq 'set') {
 if ($state.fail_set) { $global:LASTEXITCODE=1 }
 else { $state.routes=@($Arguments[1].Substring('--advertise-routes='.Length).Split(',') | Where-Object {$_}) }
} else { $global:LASTEXITCODE=1 }
$state | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $env:RR_ROUTE_TEST_STATE -Encoding UTF8
Write-Output $reply
''',encoding='utf-8-sig')
    return root,inventory,state,fake


def state_of(case):
    return json.loads(case[2].read_text(encoding='utf-8-sig'))


def set_state(case,**changes):
    data=state_of(case);data.update(changes);case[2].write_text(json.dumps(data),encoding='utf-8')


def execute(case,action='Apply',restore=None):
    root,inventory,state,fake=case
    before=set(root.glob('reports/*/route-change.json'))
    command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(SOURCE),'-Action',action,
             '-PrinterFile',str(inventory),'-ExpectedGatewayIP','100.64.0.7','-OutputDirectory',str(root/'reports'),'-TailscalePath',str(fake)]
    if restore: command+=['-RestoreFile',str(restore)]
    result=subprocess.run(command,capture_output=True,timeout=20,cwd=Path(os.environ['SystemRoot'])/'System32',env={**os.environ,'RR_ROUTE_TEST_STATE':str(state)})
    reports=set(root.glob('reports/*/route-change.json'))-before
    path=next(iter(reports)) if reports else None
    return result,(json.loads(path.read_text(encoding='utf-8')) if path else None),path


def test_plan_is_read_only_and_apply_preserves_every_existing_route(route_case):
    result,report,_=execute(route_case,'Plan')
    assert result.returncode==0,result.stderr
    assert report['status']=='plan_only' and report['mutation_attempted'] is False
    assert set(state_of(route_case)['routes'])==set(ORIGINAL)
    result,report,_=execute(route_case)
    assert result.returncode==0,result.stderr
    assert report['status']=='advertised_pending_cloud_verification'
    assert set(report['before_routes'])==set(ORIGINAL)
    assert set(report['added_routes'])==set(ADDED)
    assert set(state_of(route_case)['routes'])==set(ORIGINAL+ADDED)
    assert report['cloud_routes_verified'] is False and report['mqtt_authenticated'] is False
    mutations=[c for c in state_of(route_case)['calls'] if c.startswith('set ')]
    assert len(mutations)==1 and mutations[0].startswith('set --advertise-routes=')
    assert '--unattended' not in mutations[0] and 'up ' not in mutations[0]


def test_repeated_apply_is_noop_and_rollback_preserves_later_unrelated_routes(route_case):
    _,_,first=execute(route_case)
    result,report,_=execute(route_case)
    assert result.returncode==0 and report['status']=='already_in_requested_state'
    assert report['added_routes']==[] and report['mutation_attempted'] is False
    set_state(route_case,routes=state_of(route_case)['routes']+['10.60.0.0/16'])
    result,report,_=execute(route_case,'Rollback',first)
    assert result.returncode==0,result.stderr
    assert report['status']=='added_routes_removed'
    assert set(state_of(route_case)['routes'])==set(ORIGINAL+['10.60.0.0/16'])


@pytest.mark.parametrize('change,issue',[({'gateway':'100.64.0.8'},'wrong_gateway_or_not_logged_in'),
                                      ({'running':False},'wrong_gateway_or_not_logged_in'),
                                      ({'race':True},'routes_changed_during_preparation')])
def test_wrong_gateway_login_or_concurrent_changes_never_trigger_set(route_case,change,issue):
    set_state(route_case,**change)
    result,report,_=execute(route_case)
    assert result.returncode!=0
    assert issue.encode() in result.stderr
    assert not any(c.startswith('set ') for c in state_of(route_case)['calls'])
    if report: assert report['mutation_attempted'] is False


def test_failed_set_retains_before_snapshot_without_claiming_success(route_case):
    set_state(route_case,fail_set=True)
    result,report,_=execute(route_case)
    assert result.returncode!=0
    assert report['status']=='failed' and report['issue_code']=='tailscale_command_failed'
    assert report['mutation_attempted'] is True
    assert set(report['before_routes'])==set(ORIGINAL)
    assert set(state_of(route_case)['routes'])==set(ORIGINAL)


def test_rollback_cannot_remove_routes_outside_requested_inventory(route_case):
    _,_,first=execute(route_case)
    data=json.loads(first.read_text());data['added_routes'].append('10.20.0.0/16')
    first.write_text(json.dumps(data),encoding='utf-8')
    before=state_of(route_case)
    result,_,_=execute(route_case,'Rollback',first)
    assert result.returncode!=0 and b'restore_report_scope_mismatch' in result.stderr
    assert state_of(route_case)['routes']==before['routes']
    assert len([c for c in state_of(route_case)['calls'] if c.startswith('set ')])==1
