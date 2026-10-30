"""Exercise the actual Windows menu and child PowerShell process, without networking."""
import json
import csv
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows PowerShell entrypoint')
SOURCE = Path(__file__).resolve().parents[2] / 'deploy/three-d-printing/network'


@pytest.fixture
def launch_environment(tmp_path):
    package = tmp_path/'wechat_files'/'现场 配置包'
    package.mkdir(parents=True)
    for source,target in [('windows-site.ps1','windows-site.ps1'),('windows-start.ps1','Start.ps1')]:
        shutil.copyfile(SOURCE/source,package/target)
    (package/'Start.cmd').write_text('@echo off\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start.ps1"\n',encoding='ascii')
    fake_bin=tmp_path/'stub-bin'; fake_bin.mkdir()
    compiler=tmp_path/'compile.ps1'
    compiler.write_text('''param([string]$Target)
Add-Type -OutputType ConsoleApplication -OutputAssembly $Target -TypeDefinition @'
using System;
using System.IO;
public class Program {
    public static int Main(string[] args) {
        File.AppendAllText(Environment.GetEnvironmentVariable("RR_TEST_CALLS"),string.Join(" ",args)+"\\n");
        if(args[0]=="status") Console.WriteLine("{\\"BackendState\\":\\""+Environment.GetEnvironmentVariable("RR_TEST_VPN_STATE")+"\\"}");
        if(args[0]=="ip") Console.WriteLine("100.64.0.2");
        return 0;
    }
}
'@
''',encoding='utf-8')
    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(compiler),str(fake_bin/'tailscale.exe')],capture_output=True,check=True,timeout=30)
    env={**os.environ,'PATH':str(fake_bin)+os.pathsep+os.environ['PATH'],
         'RR_TEST_CALLS':str(tmp_path/'calls.txt')}
    return package,env


@pytest.mark.parametrize('via_menu',[True,False])
@pytest.mark.parametrize('vpn_state',['NeedsLogin','Running'])
def test_login_from_system32_and_chinese_package_path(launch_environment,via_menu,vpn_state):
    package,env=launch_environment
    env['RR_TEST_VPN_STATE']=vpn_state
    command=(['cmd.exe','/d','/c','call',str(package/'Start.cmd')] if via_menu else
        ['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(package/'windows-site.ps1'),'-Action','Login'])
    result=subprocess.run(command,input=b'3\r\n\r\n' if via_menu else b'',capture_output=True,
        cwd=Path(os.environ['SystemRoot'])/'System32',env=env,timeout=30)
    assert result.returncode==0,result.stderr.decode(errors='replace')
    assert b'Join-Path' not in result.stderr,result.stderr
    calls=Path(env['RR_TEST_CALLS']).read_text().splitlines()
    assert calls[0]=='status --json'
    assert calls[1]==('set --unattended=true' if vpn_state=='Running' else
        'up --unattended --accept-dns=false --timeout=60s')
    assert calls[2]=='ip -4'


@pytest.mark.parametrize('count', [11, 16])
def test_printer_inventory_and_host_route_plan_support_complete_fleet(tmp_path, count):
    rows = [{'machine_no':n, 'ip':f'192.168.110.{100+n}', 'credential_ref':f'printer-{n:02}'} for n in range(1,count+1)]
    if count == 16:
        rows[5]['credential_ref'], rows[11]['credential_ref'] = rows[11]['credential_ref'], rows[5]['credential_ref']
    inventory = tmp_path/'printers.csv'
    with inventory.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    runner = tmp_path/'validate.ps1'
    runner.write_text('''param([string]$Source,[string]$PrinterFile,[string]$OutputPath)
$ErrorActionPreference='Stop'
$tokens=$null; $parseErrors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $Source 'windows-site.ps1'),[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw 'Parse error' }
$reader=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Read-Printers'},$true)
. ([scriptblock]::Create($reader.Extent.Text))
$printers=@(Read-Printers)
& (Join-Path $Source 'windows-tailscale-plan.ps1') -PrinterIPs @($printers | ForEach-Object { $_.ip }) -OutputPath $OutputPath | Out-Null
ConvertTo-Json -InputObject $printers -Compress
''', encoding='utf-8-sig')
    output = tmp_path/'plan.json'
    command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(runner),str(SOURCE),str(inventory),str(output)]
    result=subprocess.run(command,capture_output=True,timeout=30)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    observed=json.loads(result.stdout)
    assert [p['credential_ref'] for p in observed] == [p['credential_ref'] for p in rows]
    plan=json.loads(output.read_text(encoding='utf-8'))
    assert plan['mode'] == 'plan_only_no_network_changes'
    assert plan['reviewed_command'].count('/32') == count
    assert '/24' not in plan['reviewed_command']


@pytest.mark.parametrize('fault', ['missing_reference','duplicate_reference','duplicate_address','out_of_range'])
def test_expanded_inventory_rejects_ambiguous_identity_without_networking(tmp_path, fault):
    rows = [{'machine_no':n, 'ip':f'192.168.110.{100+n}', 'credential_ref':f'printer-{n:02}'} for n in range(1,17)]
    if fault == 'missing_reference': rows[-1]['credential_ref']=''
    elif fault == 'duplicate_reference': rows[-1]['credential_ref']=rows[0]['credential_ref']
    elif fault == 'duplicate_address': rows[-1]['ip']=rows[0]['ip']
    else: rows[-1]['machine_no']=17
    inventory=tmp_path/'printers.csv'
    with inventory.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    runner=tmp_path/'validate.ps1'
    runner.write_text('''param([string]$Source,[string]$PrinterFile)
$ErrorActionPreference='Stop'
$tokens=$null; $parseErrors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $Source 'windows-site.ps1'),[ref]$tokens,[ref]$parseErrors)
$reader=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Read-Printers'},$true)
. ([scriptblock]::Create($reader.Extent.Text))
Read-Printers | Out-Null
''',encoding='utf-8-sig')
    result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(runner),str(SOURCE),str(inventory)],capture_output=True,timeout=30)
    assert result.returncode != 0
