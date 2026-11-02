[CmdletBinding()]
param(
    [string]$PrinterFile,
    [string]$OutputDirectory,
    [string]$Subnet = '192.168.110.0/24',
    [string]$ExpectedGatewayIP,
    [ValidateRange(500,5000)][int]$ProbeTimeoutMs = 2000,
    [ValidateRange(1,4)][int]$Concurrency = 4
)
$ErrorActionPreference = 'Stop'
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $PrinterFile) { $PrinterFile = Join-Path $scriptDirectory 'expected-printers.csv' }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $scriptDirectory 'reports' }

function Read-DiscoveryInventory {
    $rows = @(Import-Csv -LiteralPath $PrinterFile)
    if ($rows.Count -lt 1 -or $rows.Count -gt 16) { throw 'invalid_inventory' }
    $numbers=@(); $refs=@(); $pins=@()
    foreach ($row in $rows) {
        $number=[int]$row.machine_no
        if ($number -lt 1 -or $number -gt 16 -or $number -in $numbers) { throw 'invalid_machine_number' }
        if ($row.credential_ref -notmatch '^printer-[0-9]{2}$' -or $row.credential_ref -in $refs) { throw 'invalid_credential_reference' }
        if ($row.cert_sha256 -cnotmatch '^[a-f0-9]{64}$' -or $row.cert_sha256 -in $pins) { throw 'invalid_or_duplicate_certificate_pin' }
        $ip=[Net.IPAddress]::Parse($row.ip)
        if ($ip.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or $ip.ToString() -cne $row.ip) { throw 'invalid_prior_ip' }
        $numbers+=$number; $refs+=$row.credential_ref; $pins+=$row.cert_sha256
    }
    return $rows
}

function Read-DiscoveryPrefix {
    if ($Subnet -notmatch '^([0-9]+\.[0-9]+\.[0-9]+)\.0/24$') { throw 'private_slash24_required' }
    $ip=[Net.IPAddress]::Parse($Subnet.Split('/')[0]); $b=$ip.GetAddressBytes()
    if ($b.Length -ne 4 -or $ip.ToString() -cne $Subnet.Split('/')[0] -or
        -not ($b[0] -eq 10 -or ($b[0] -eq 172 -and $b[1] -ge 16 -and $b[1] -le 31) -or ($b[0] -eq 192 -and $b[1] -eq 168))) { throw 'private_slash24_required' }
    return "$($b[0]).$($b[1]).$($b[2])."
}

function Convert-DiscoveryMatches($Inventory,$Observations) {
    foreach ($row in $Inventory) {
        $matches=@($Observations | Where-Object { $_.Fingerprint -ceq $row.cert_sha256 } | Select-Object -ExpandProperty IP -Unique | Sort-Object)
        $status=if($matches.Count -eq 1){'matched'}elseif($matches.Count -gt 1){'ambiguous'}else{'not_found'}
        [ordered]@{
            machine_no=[int]$row.machine_no; credential_ref=$row.credential_ref; previous_ip=$row.ip
            status=$status; current_ip=if($matches.Count -eq 1){$matches[0]}else{$null}
            candidate_ips=$matches; certificate_sha256=$row.cert_sha256
            address_changed=if($matches.Count -eq 1){$matches[0] -cne $row.ip}else{$null}
        }
    }
}

# TCP 8883 and a TLS handshake only. The certificate is matched by its full
# existing SHA-256 pin; names/serials are never extracted and no application
# bytes, credentials, MQTT packets or printer commands are sent.
$probeSource = @'
using System;
using System.Net;
using System.Net.Sockets;
using System.Net.Security;
using System.Security.Authentication;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
public static class RRPrinterAddressDiscovery {
    public sealed class Observation {
        public string IP;
        public bool Tcp;
        public string Fingerprint = "";
    }
    public static Observation Probe(string localIP, int interfaceIndex, string ip, int port, int timeoutMs) {
        var result=new Observation { IP=ip };
        using (var tcp=new TcpClient(AddressFamily.InterNetwork)) {
            try {
                tcp.Client.Bind(new IPEndPoint(IPAddress.Parse(localIP),0));
                if (interfaceIndex > 0)
                    tcp.Client.SetSocketOption(SocketOptionLevel.IP,(SocketOptionName)31,IPAddress.HostToNetworkOrder(interfaceIndex));
                var connect=tcp.BeginConnect(IPAddress.Parse(ip),port,null,null);
                using (var wait=connect.AsyncWaitHandle) {
                    if (!wait.WaitOne(timeoutMs)) return result;
                    tcp.EndConnect(connect);
                }
                result.Tcp=true;
                using (var ssl=new SslStream(tcp.GetStream(),false,delegate { return true; })) {
                    var handshake=ssl.BeginAuthenticateAsClient(ip,null,SslProtocols.Tls12,false,null,null);
                    using (var wait=handshake.AsyncWaitHandle) {
                        if (!wait.WaitOne(timeoutMs)) return result;
                        ssl.EndAuthenticateAsClient(handshake);
                    }
                    using (var hash=SHA256.Create())
                        result.Fingerprint=BitConverter.ToString(hash.ComputeHash(ssl.RemoteCertificate.GetRawCertData())).Replace("-","").ToLowerInvariant();
                }
            } catch { /* Return stage booleans, never raw certificate/error text. */ }
        }
        return result;
    }
    public static Observation[] Scan(string localIP,int interfaceIndex,string[] ips,int timeoutMs,int concurrency) {
        var results=new Observation[ips.Length]; int completed=0;
        Parallel.For(0,ips.Length,new ParallelOptions { MaxDegreeOfParallelism=concurrency },i => {
            results[i]=Probe(localIP,interfaceIndex,ips[i],8883,timeoutMs);
            int count=Interlocked.Increment(ref completed);
            if (count%32==0 || count==ips.Length) Console.WriteLine("Checked {0}/{1} addresses",count,ips.Length);
        });
        return results;
    }
}
'@

$report=[ordered]@{ version=1; purpose='find_known_printer_certificates_no_mqtt'; observed_at=$null; status='not_started'; subnet=$Subnet; source_ip=$null; interface_index=$null; gateway_identity_verified=$false; port=8883; settings_changed=$false; application_bytes_sent=0; printers=@(); issue_code='' }
$reportPath=$null
try {
    $inventory=@(Read-DiscoveryInventory)
    $prefix=Read-DiscoveryPrefix
    if (@($inventory | Where-Object { -not $_.ip.StartsWith($prefix) }).Count) { throw 'prior_ip_outside_subnet' }
    if (-not $ExpectedGatewayIP) { throw 'expected_gateway_required' }
    $tailscale=Get-Command tailscale.exe -ErrorAction SilentlyContinue
    $tailPath=if($tailscale){$tailscale.Source}else{Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'}
    if (-not (Test-Path -LiteralPath $tailPath -PathType Leaf)) { throw 'tailscale_not_installed' }
    $tailState=& $tailPath status --json 2>$null | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $tailState.BackendState -ne 'Running' -or $ExpectedGatewayIP -notin @($tailState.Self.TailscaleIPs)) { throw 'wrong_gateway_or_not_logged_in' }
    $report.gateway_identity_verified=$true
    $interfaces=@(Get-NetIPInterface -AddressFamily IPv4 | Where-Object { [string]$_.ConnectionState -eq 'Connected' })
    $addresses=@(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.IPAddress.StartsWith($prefix) -and $_.PrefixLength -eq 24 -and
        [string]$_.AddressState -eq 'Preferred' -and $_.InterfaceIndex -in @($interfaces.InterfaceIndex)
    })
    if ($addresses.Count -ne 1) { throw 'connect_one_interface_to_printer_subnet' }
    $local=$addresses[0]
    $report.source_ip=$local.IPAddress; $report.interface_index=$local.InterfaceIndex
    $targets=@(1..254 | ForEach-Object { $prefix+$_ } | Where-Object { $_ -ne $local.IPAddress })
    # Refuse a route through a VPN/default gateway even if a matching local
    # address remains configured on a disconnected or incorrectly routed NIC.
    $route=@(Find-NetRoute -RemoteIPAddress ($prefix+'1') | Where-Object { $_.DestinationPrefix })
    if ($route.Count -ne 1 -or $route[0].InterfaceIndex -ne $local.InterfaceIndex -or $route[0].DestinationPrefix -ne $Subnet -or $route[0].NextHop -ne '0.0.0.0') { throw 'printer_subnet_not_directly_connected' }
    if (-not ('RRPrinterAddressDiscovery' -as [type])) { Add-Type -TypeDefinition $probeSource }
    $report.status='scanning'
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $reportPath=Join-Path $OutputDirectory ('printer-addresses-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'.json')
    Write-Output 'Checking only the connected printer /24 subnet, TCP 8883. This usually takes 2-3 minutes.'
    $observations=@([RRPrinterAddressDiscovery]::Scan($local.IPAddress,$local.InterfaceIndex,[string[]]$targets,$ProbeTimeoutMs,$Concurrency))
    $report.printers=@(Convert-DiscoveryMatches $inventory $observations)
    $report.scanned_address_count=$targets.Count
    $report.tcp_response_count=@($observations | Where-Object { $_.Tcp }).Count
    $report.certificate_response_count=@($observations | Where-Object { $_.Fingerprint }).Count
    $report.unrecognized_certificate_count=@($observations | Where-Object { $_.Fingerprint -and $_.Fingerprint -cnotin @($inventory.cert_sha256) }).Count
    # No identities or addresses of unrecognized certificates enter the report.
    $report.status=if(@($report.printers | Where-Object { $_.status -ne 'matched' }).Count){'partial_or_ambiguous'}else{'complete'}
} catch {
    $allowed=@('invalid_inventory','invalid_machine_number','invalid_credential_reference','invalid_or_duplicate_certificate_pin','invalid_prior_ip','private_slash24_required','prior_ip_outside_subnet','expected_gateway_required','tailscale_not_installed','wrong_gateway_or_not_logged_in','connect_one_interface_to_printer_subnet','printer_subnet_not_directly_connected')
    $report.issue_code=if($_.Exception.Message -in $allowed){$_.Exception.Message}else{'discovery_failed'}
    $report.status='failed'
}
$report.observed_at=(Get-Date).ToUniversalTime().ToString('o')
if (-not $reportPath) {
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $reportPath=Join-Path $OutputDirectory ('printer-addresses-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'.json')
}
[IO.File]::WriteAllText($reportPath,($report | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
$report.printers | ForEach-Object { [pscustomobject]$_ } | Format-Table machine_no,previous_ip,current_ip,status
Write-Output ('Report: '+$reportPath)
if ($report.status -eq 'failed') { [Console]::Error.WriteLine('Stopped: '+$report.issue_code); exit 1 }
