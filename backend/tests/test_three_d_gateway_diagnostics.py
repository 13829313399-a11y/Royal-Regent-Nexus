"""Verify the field diagnostic projection without touching real network settings."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows PowerShell handoff')
SOURCE = Path(__file__).resolve().parents[2] / 'deploy/three-d-printing/network/windows-site.ps1'


@pytest.mark.parametrize('unavailable', [False, True])
def test_gateway_diagnostics_are_read_only_redacted_and_preserve_unknowns(tmp_path, unavailable):
    fake = tmp_path / 'tailscale.ps1'
    fake.write_text('''param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments)
Add-Content -LiteralPath $env:RR_DIAGNOSTIC_CALLS -Value ($Arguments -join ' ')
$global:LASTEXITCODE=0
if ($env:RR_DIAGNOSTIC_UNAVAILABLE -eq 'true') { $global:LASTEXITCODE=1; Write-Output 'secret-sentinel'; return }
'{"WantRunning":true,"ShieldsUp":true,"RouteAll":false,"AdvertiseRoutes":["192.168.110.12/32"],"NoSNAT":false,"Persist":{"PrivateNodeKey":"secret-sentinel"},"AuthKey":"secret-sentinel","UnknownFutureField":"secret-sentinel"}'
''', encoding='utf-8-sig')
    runner = tmp_path / 'runner.ps1'
    runner.write_text('''param([string]$Source,[string]$Fake,[string]$Output)
$ErrorActionPreference='Stop'
$tokens=$null; $parseErrors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($Source,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw 'Parse error' }
$reader=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Read-GatewayDiagnostics'},$true)
. ([scriptblock]::Create($reader.Extent.Text))
function Get-NetIPInterface { [pscustomobject]@{InterfaceIndex=4;InterfaceAlias='LAN';ConnectionState='Connected';Forwarding='Disabled';InterfaceMetric=20;Hidden='secret-sentinel'} }
function Find-NetRoute {
 param($RemoteIPAddress)
 if ($RemoteIPAddress -eq '192.168.110.107') { throw 'secret-sentinel' }
 [pscustomobject]@{IPAddress='192.168.110.2';InterfaceIndex=4;InterfaceAlias='LAN';DestinationPrefix='192.168.110.0/24';NextHop='0.0.0.0';RouteMetric=0;Hidden='secret-sentinel'}
}
function Get-NetNeighbor {
 [pscustomobject]@{IPAddress='192.168.110.106';InterfaceIndex=4;State='Reachable';LinkLayerAddress='secret-sentinel'}
 [pscustomobject]@{IPAddress='192.168.110.254';InterfaceIndex=4;State='Reachable';LinkLayerAddress='secret-sentinel'}
}
function Get-NetFirewallProfile {
 if ($env:RR_DIAGNOSTIC_UNAVAILABLE -eq 'true') { throw 'secret-sentinel' }
 [pscustomobject]@{Name='Private';Enabled='True';DefaultInboundAction='Block';DefaultOutboundAction='Allow';AllowInboundRules='True';AllowLocalFirewallRules='True'}
}
function Get-NetFirewallRule {
 [pscustomobject]@{DisplayName='Tailscale';Enabled='True';Direction='Inbound';Action='Allow';Profile='Any';Description='secret-sentinel'}
 [pscustomobject]@{DisplayName='Other app';Enabled='True';Direction='Inbound';Action='Allow';Profile='Any'}
}
$tailscale=$Fake
$printers=@(1..16 | ForEach-Object { [pscustomobject]@{machine_no=$_;ip=('192.168.110.'+(100+$_))} })
$result=Read-GatewayDiagnostics
[IO.File]::WriteAllText($Output,($result | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
''', encoding='utf-8-sig')
    output, calls = tmp_path / 'report.json', tmp_path / 'calls.txt'
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(runner), str(SOURCE), str(fake), str(output)],
        capture_output=True, timeout=20,
        env={**os.environ, 'RR_DIAGNOSTIC_CALLS': str(calls), 'RR_DIAGNOSTIC_UNAVAILABLE': str(unavailable).lower()},
    )
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    raw = output.read_text(encoding='utf-8')
    assert 'secret-sentinel' not in raw
    assert b'secret-sentinel' not in result.stdout + result.stderr
    assert calls.read_text().splitlines() == ['debug prefs']
    report = json.loads(raw)
    assert report['mode'] == 'read_only'
    assert len(report['selected_routes']) == 16
    assert report['selected_routes'][6] == {'machine_no': 7, 'ip': '192.168.110.107', 'status': 'unavailable', 'selected': []}
    assert report['selected_routes'][5]['selected'][0]['alias'] == 'LAN'
    assert report['neighbors'] == [{'ip': '192.168.110.106', 'interface_index': 4, 'state': 'Reachable'}]
    assert len(report['tailscale_firewall_rules']) == 1
    if unavailable:
        assert report['preferences'] is None
        assert report['firewall_profiles'] == []
        assert set(report['issue_codes']) == {'tailscale_preferences_unavailable', 'firewall_profiles_unavailable'}
    else:
        assert report['preferences']['ShieldsUp'] is True
        assert report['preferences']['AdvertiseRoutes'] == ['192.168.110.12/32']
        assert not report['issue_codes']
