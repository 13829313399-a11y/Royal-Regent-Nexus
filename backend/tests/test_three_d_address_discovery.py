"""Bounded certificate discovery: real TLS without device login, strict identity mapping."""
import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest

from test_three_d_studio_collection import certificate_peer

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows field discovery')
SOURCE = Path(__file__).resolve().parents[2] / 'deploy/three-d-printing/network/rediscover-printer-addresses.ps1'


def powershell(script, tmp_path, *args):
    runner = tmp_path / 'runner.ps1'
    runner.write_text(script, encoding='utf-8-sig')
    return subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(runner), str(SOURCE), *map(str, args)], capture_output=True, timeout=25)


LOAD_FUNCTIONS = '''param([string]$Source,[string]$CaseFile)
$ErrorActionPreference='Stop'
$tokens=$null; $parseErrors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($Source,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw 'parse_failed' }
foreach ($name in @('Read-DiscoveryInventory','Read-DiscoveryPrefix','Convert-DiscoveryMatches')) {
 $definition=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
 . ([scriptblock]::Create($definition.Extent.Text))
}
$case=Get-Content -LiteralPath $CaseFile -Raw | ConvertFrom-Json
'''


def test_moved_addresses_preserve_device_references_and_reject_ambiguity(tmp_path):
    case = tmp_path / 'case.json'
    case.write_text(json.dumps({'inventory': [
        {'machine_no': 6, 'ip': '192.168.110.12', 'credential_ref': 'printer-12', 'cert_sha256': 'a'*64},
        {'machine_no': 9, 'ip': '192.168.110.84', 'credential_ref': 'printer-06', 'cert_sha256': 'b'*64},
        {'machine_no': 16, 'ip': '192.168.110.116', 'credential_ref': 'printer-16', 'cert_sha256': 'c'*64},
    ], 'observations': [
        {'IP': '192.168.110.11', 'Fingerprint': 'a'*64},
        {'IP': '192.168.110.91', 'Fingerprint': 'b'*64},
        {'IP': '192.168.110.92', 'Fingerprint': 'b'*64},
        {'IP': '192.168.110.222', 'Fingerprint': 'd'*64, 'Serial': 'UNRELATED_SECRET'},
    ]}), encoding='utf-8')
    result = powershell(LOAD_FUNCTIONS + 'ConvertTo-Json -InputObject @(Convert-DiscoveryMatches $case.inventory $case.observations) -Depth 8', tmp_path, case)
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)
    assert rows[0]['current_ip'] == '192.168.110.11'
    assert rows[0]['credential_ref'] == 'printer-12' and rows[0]['address_changed']
    assert rows[1]['status'] == 'ambiguous' and rows[1]['current_ip'] is None
    assert rows[1]['candidate_ips'] == ['192.168.110.91', '192.168.110.92']
    assert rows[2]['status'] == 'not_found' and rows[2]['address_changed'] is None
    assert b'192.168.110.222' not in result.stdout and b'UNRELATED_SECRET' not in result.stdout


@pytest.mark.parametrize('subnet', ['0.0.0.0/24', '8.8.8.0/24', '192.168.110.0/16', '192.168.110.1/24', '192.168.011.0/24'])
def test_discovery_refuses_public_broad_or_noncanonical_subnets(tmp_path, subnet):
    case = tmp_path / 'case.json'
    case.write_text(json.dumps({'subnet': subnet}), encoding='utf-8')
    result = powershell(LOAD_FUNCTIONS + '$Subnet=$case.subnet; Read-DiscoveryPrefix', tmp_path, case)
    assert result.returncode != 0


def test_duplicate_pins_cannot_assign_one_identity_to_two_machines(tmp_path):
    inventory = tmp_path / 'printers.csv'
    with inventory.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['machine_no','ip','credential_ref','cert_sha256'])
        writer.writerows([(6,'192.168.110.12','printer-12','a'*64),(7,'192.168.110.152','printer-13','a'*64)])
    case = tmp_path / 'case.json'
    case.write_text(json.dumps({'inventory': str(inventory)}), encoding='utf-8')
    result = powershell(LOAD_FUNCTIONS + '$PrinterFile=$case.inventory; Read-DiscoveryInventory', tmp_path, case)
    assert result.returncode != 0
    assert b'invalid_or_duplicate_certificate_pin' in result.stderr


@pytest.mark.parametrize('stalled', [False, True])
def test_real_tls_is_bounded_sends_no_application_bytes_and_honors_source_binding(tmp_path, stalled):
    with certificate_peer(tmp_path, serial='PRIVATE-SERIAL-NOT-EXPORTED', stalled=stalled) as (port, pin, received):
        runner = '''param([string]$Source,[int]$Port)
$ErrorActionPreference='Stop'
$text=Get-Content -LiteralPath $Source -Raw
$match=[regex]::Match($text,"(?s)\\$probeSource = @'\\r?\\n(.*?)\\r?\\n'@")
if (-not $match.Success) { throw 'probe_source_missing' }
Add-Type -TypeDefinition $match.Groups[1].Value
$index=(Get-NetIPAddress -AddressFamily IPv4 -IPAddress '127.0.0.1').InterfaceIndex
$result=[RRPrinterAddressDiscovery]::Probe('127.0.0.1',$index,'127.0.0.1',$Port,700)
$result | ConvertTo-Json -Compress
'''
        # A single quoted regex avoids PowerShell interpolation of $probeSource.
        runner = runner.replace('"(?s)\\$probeSource = @\'\\r?\\n(.*?)\\r?\\n\'@"', "'(?s)\\$probeSource = @''\\r?\\n(.*?)\\r?\\n''@'")
        result = powershell(runner, tmp_path, port)
        assert result.returncode == 0, result.stderr.decode(errors='replace')
        observed = json.loads(result.stdout)
        assert observed['Tcp'] is True
        assert observed['Fingerprint'] == ('' if stalled else pin)
        assert b'PRIVATE-SERIAL-NOT-EXPORTED' not in result.stdout + result.stderr
    assert received == ([] if stalled else [b''])


def test_entrypoint_refuses_wrong_gateway_without_network_probes(tmp_path):
    # Execute the real entrypoint in a child PowerShell process. Its mocked
    # Tailscale result disagrees with the expected gateway; any network cmdlet
    # or Add-Type call would fail this test before the guarded exit.
    inventory = tmp_path / 'printers.csv'
    inventory.write_text('machine_no,ip,credential_ref,cert_sha256\n6,192.168.110.12,printer-12,'+'a'*64+'\n', encoding='utf-8')
    fake = tmp_path / 'tailscale.ps1'
    fake.write_text("$global:LASTEXITCODE=0; '{\"BackendState\":\"Running\",\"Self\":{\"TailscaleIPs\":[\"100.64.0.8\"]}}'", encoding='utf-8')
    runner = '''param([string]$Source,[string]$Inventory,[string]$Fake,[string]$Output)
$ErrorActionPreference='Stop'
function Get-Command { [pscustomobject]@{Source=$Fake} }
function Get-NetIPInterface { throw 'UNEXPECTED_NETWORK_QUERY' }
function Add-Type { throw 'UNEXPECTED_PROBE' }
& $Source -PrinterFile $Inventory -ExpectedGatewayIP '100.64.0.7' -OutputDirectory $Output
exit $LASTEXITCODE
'''
    output = tmp_path / 'reports'
    result = powershell(runner, tmp_path, inventory, fake, output)
    assert result.returncode == 1
    report = json.loads(next(output.glob('printer-addresses-*.json')).read_text(encoding='utf-8'))
    assert report['issue_code'] == 'wrong_gateway_or_not_logged_in'
    assert report['application_bytes_sent'] == 0 and report['settings_changed'] is False
    assert not report['printers']
    assert b'UNEXPECTED' not in result.stdout + result.stderr


@pytest.mark.parametrize('fault', ['wrong_interface', 'wrong_route', 'none'])
def test_real_entrypoint_binds_a_direct_private_subnet_and_exports_only_known_matches(tmp_path, fault):
    inventory = tmp_path / 'printers.csv'
    inventory.write_text('machine_no,ip,credential_ref,cert_sha256\n6,192.168.110.12,printer-12,'+'a'*64+'\n', encoding='utf-8')
    fake = tmp_path / 'tailscale.ps1'
    fake.write_text("$global:LASTEXITCODE=0; '{\"BackendState\":\"Running\",\"Self\":{\"TailscaleIPs\":[\"100.64.0.7\"]}}'", encoding='utf-8')
    runner = '''param([string]$Source,[string]$Inventory,[string]$Fake,[string]$Output,[string]$Fault)
$ErrorActionPreference='Stop'
function Get-Command { [pscustomobject]@{Source=$Fake} }
function Get-NetIPInterface { [pscustomobject]@{InterfaceIndex=19;ConnectionState='Connected'} }
function Get-NetIPAddress { [pscustomobject]@{IPAddress=if($Fault -eq 'wrong_interface'){'192.168.15.145'}else{'192.168.110.40'};PrefixLength=24;AddressState='Preferred';InterfaceIndex=19} }
function Find-NetRoute { [pscustomobject]@{DestinationPrefix=if($Fault -eq 'wrong_route'){'0.0.0.0/0'}else{'192.168.110.0/24'};NextHop='0.0.0.0';InterfaceIndex=19} }
Add-Type -TypeDefinition @'
using System;
public static class RRPrinterAddressDiscovery {
 public class Observation { public string IP; public bool Tcp=true; public string Fingerprint; }
 public static Observation[] Scan(string source,int index,string[] ips,int timeout,int concurrency) {
  if(source!="192.168.110.40" || index!=19 || ips.Length!=253 || timeout!=500 || concurrency!=4) throw new Exception("scope_mismatch");
  foreach(var ip in ips) if(!ip.StartsWith("192.168.110.") || ip==source || ip.EndsWith(".0") || ip.EndsWith(".255")) throw new Exception("scope_mismatch");
  return new [] {new Observation {IP="192.168.110.11",Fingerprint=new string('a',64)},new Observation {IP="192.168.110.222",Fingerprint=new string('b',64)}};
 }
}
'@
& $Source -PrinterFile $Inventory -ExpectedGatewayIP '100.64.0.7' -OutputDirectory $Output -ProbeTimeoutMs 500
exit $LASTEXITCODE
'''
    output = tmp_path / 'reports'
    result = powershell(runner, tmp_path, inventory, fake, output, fault)
    report = json.loads(next(output.glob('printer-addresses-*.json')).read_text(encoding='utf-8'))
    if fault != 'none':
        assert result.returncode == 1
        assert report['issue_code'] == ('connect_one_interface_to_printer_subnet' if fault == 'wrong_interface' else 'printer_subnet_not_directly_connected')
        assert not report['printers']
    else:
        assert result.returncode == 0, result.stderr
        assert report['status'] == 'complete', report
        assert report['scanned_address_count'] == 253
        assert report['unrecognized_certificate_count'] == 1
        assert report['printers'][0]['current_ip'] == '192.168.110.11'
        assert '192.168.110.222' not in json.dumps(report)
        assert b'192.168.110.222' not in result.stdout
    assert report['settings_changed'] is False and report['application_bytes_sent'] == 0
