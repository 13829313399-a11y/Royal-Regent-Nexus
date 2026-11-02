[CmdletBinding()]
param(
    [ValidateSet('Inspect','Install','Login','Routes')][string]$Action = 'Inspect',
    [string]$PrinterFile,
    [string]$OutputDirectory,
    [switch]$IncludeGatewayDiagnostics
)
$ErrorActionPreference = 'Stop'
$siteDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $PrinterFile) { $PrinterFile = Join-Path $siteDirectory 'printers.csv' }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $siteDirectory 'reports' }
$utf8 = [Text.UTF8Encoding]::new($false)
function Find-Tailscale {
    $command = Get-Command tailscale.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $installed = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
    if (Test-Path -LiteralPath $installed) { return $installed }
    return $null
}
function Read-Printers {
    $rows = @(Import-Csv -LiteralPath $PrinterFile)
    if ($rows.Count -lt 1 -or $rows.Count -gt 16) { throw 'Fill printers.csv with one to sixteen distinct machines.' }
    $numbers = @(); $addresses = @(); $references = @()
    foreach ($row in $rows) {
        $ip = [Net.IPAddress]::Parse($row.ip)
        $b = $ip.GetAddressBytes()
        if ($b.Length -ne 4 -or -not ($b[0] -eq 10 -or ($b[0] -eq 172 -and $b[1] -ge 16 -and $b[1] -le 31) -or ($b[0] -eq 192 -and $b[1] -eq 168))) { throw 'Use the printer LAN IPv4 address.' }
        $number = [int]$row.machine_no
        if ($number -lt 1 -or $number -gt 16 -or $numbers -contains $number -or $addresses -contains $ip.ToString()) { throw 'Duplicate or invalid printer number/address.' }
        if ($rows.Count -gt 11 -and -not $row.credential_ref) { throw 'Expanded fleets require explicit credential_ref values tied to physical devices.' }
        if ($row.credential_ref) {
            if ($row.credential_ref -notmatch '^printer-[0-9]{2}$' -or $references -contains $row.credential_ref) { throw 'Duplicate or invalid device credential reference.' }
            $references += $row.credential_ref
        }
        $numbers += $number; $addresses += $ip.ToString()
    }
    return $rows
}
function Read-GatewayDiagnostics {
    # Project only non-secret fields. Never export raw prefs/netmap, which can
    # contain authentication material. These queries do not change networking.
    $diagnostic = [ordered]@{ mode='read_only'; issue_codes=@(); preferences=$null; interfaces=@(); selected_routes=@(); neighbors=@(); firewall_profiles=@(); tailscale_firewall_rules=@() }
    if ($tailscale) {
        try {
            $raw = & $tailscale debug prefs 2>$null | Out-String
            if ($LASTEXITCODE -ne 0) { throw 'preferences_unavailable' }
            $prefs = $raw | ConvertFrom-Json
            $diagnostic.preferences = [ordered]@{}
            foreach ($key in @('WantRunning','ShieldsUp','RouteAll','AdvertiseRoutes','NoSNAT','NoStatefulFiltering','ExitNodeIP','ExitNodeAllowLANAccess')) {
                if ($null -ne $prefs.PSObject.Properties[$key]) { $diagnostic.preferences[$key] = $prefs.$key }
            }
        } catch { $diagnostic.issue_codes += 'tailscale_preferences_unavailable' }
        finally { $raw=$null; $prefs=$null }
    } else { $diagnostic.issue_codes += 'tailscale_not_installed' }
    try {
        $diagnostic.interfaces = @(Get-NetIPInterface -AddressFamily IPv4 -ErrorAction Stop | ForEach-Object {
            [ordered]@{ interface_index=$_.InterfaceIndex; alias=$_.InterfaceAlias; state=[string]$_.ConnectionState; forwarding=[string]$_.Forwarding; metric=$_.InterfaceMetric }
        })
    } catch { $diagnostic.issue_codes += 'interfaces_unavailable' }
    foreach ($row in $printers) {
        try {
            $selected = @(Find-NetRoute -RemoteIPAddress $row.ip -ErrorAction Stop | ForEach-Object {
                [ordered]@{ source_ip=$_.IPAddress; interface_index=$_.InterfaceIndex; alias=$_.InterfaceAlias; destination_prefix=$_.DestinationPrefix; next_hop=$_.NextHop; route_metric=$_.RouteMetric }
            })
            $diagnostic.selected_routes += [ordered]@{ machine_no=[int]$row.machine_no; ip=$row.ip; status='observed'; selected=$selected }
        } catch { $diagnostic.selected_routes += [ordered]@{ machine_no=[int]$row.machine_no; ip=$row.ip; status='unavailable'; selected=@() } }
    }
    try {
        $diagnostic.neighbors = @(Get-NetNeighbor -AddressFamily IPv4 -ErrorAction Stop | Where-Object { $_.IPAddress -in @($printers.ip) } | ForEach-Object {
            [ordered]@{ ip=$_.IPAddress; interface_index=$_.InterfaceIndex; state=[string]$_.State }
        })
    } catch { $diagnostic.issue_codes += 'neighbors_unavailable' }
    try {
        $diagnostic.firewall_profiles = @(Get-NetFirewallProfile -ErrorAction Stop | ForEach-Object {
            [ordered]@{ name=$_.Name; enabled=[string]$_.Enabled; inbound=[string]$_.DefaultInboundAction; outbound=[string]$_.DefaultOutboundAction; allow_inbound_rules=[string]$_.AllowInboundRules; allow_local_rules=[string]$_.AllowLocalFirewallRules }
        })
    } catch { $diagnostic.issue_codes += 'firewall_profiles_unavailable' }
    try {
        $diagnostic.tailscale_firewall_rules = @(Get-NetFirewallRule -PolicyStore ActiveStore -ErrorAction Stop | Where-Object { $_.DisplayName -like '*Tailscale*' } | ForEach-Object {
            [ordered]@{ name=$_.DisplayName; enabled=[string]$_.Enabled; direction=[string]$_.Direction; action=[string]$_.Action; profile=[string]$_.Profile }
        })
    } catch { $diagnostic.issue_codes += 'firewall_rules_unavailable' }
    return $diagnostic
}
$tailscale = Find-Tailscale
if ($Action -eq 'Install') {
    if ($tailscale) { Write-Output "Already installed: $tailscale"; exit 0 }
    $architecture = $env:PROCESSOR_ARCHITECTURE.ToLowerInvariant()
    $installer = Get-ChildItem -LiteralPath $siteDirectory -Filter "tailscale-*-$architecture.msi" | Select-Object -First 1
    if ($installer) {
        $result = Start-Process msiexec.exe -ArgumentList @('/i',('"' + $installer.FullName + '"'),'/qn','/norestart') -WindowStyle Hidden -PassThru -Wait
        if ($result.ExitCode -notin @(0,3010)) { throw "Tailscale install failed: $($result.ExitCode)" }
    } else {
        if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) { throw 'Download the Windows installer from https://tailscale.com/download/windows and install it, then run Login.' }
        & winget.exe install --id Tailscale.Tailscale --exact --source winget --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw 'Tailscale installation failed.' }
    }
    Write-Output 'Installed. Next: windows-site.ps1 -Action Login'
    exit 0
}
if ($Action -eq 'Login') {
    if (-not $tailscale) { throw 'Run Install first.' }
    $state = (& $tailscale status --json | ConvertFrom-Json).BackendState
    if ($state -eq 'Running') {
        & $tailscale set --unattended=true
    } else {
        & $tailscale up --unattended --accept-dns=false --timeout=60s
    }
    if ($LASTEXITCODE -ne 0) { throw 'Complete the browser login, then run Login again.' }
    & $tailscale ip -4
    exit 0
}
$printers = Read-Printers
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
if ($Action -eq 'Routes') {
    if (-not $tailscale) { throw 'Run Install and Login first.' }
    if ((& $tailscale status --json | ConvertFrom-Json).BackendState -ne 'Running') { throw 'Run Login first.' }
    $prefs = & $tailscale debug prefs | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Could not read existing routes.' }
    $previous = @($prefs.AdvertiseRoutes | Where-Object { $_ })
    $routes = @(@($previous) + @($printers | ForEach-Object { "$($_.ip)/32" }) | Sort-Object -Unique)
    [IO.File]::WriteAllText((Join-Path $OutputDirectory "routes-before-$stamp.json"), (ConvertTo-Json -InputObject $previous), $utf8)
    & $tailscale set "--advertise-routes=$($routes -join ',')" --unattended=true
    if ($LASTEXITCODE -ne 0) { throw 'Route advertisement failed.' }
    Write-Output 'Routes advertised. Enable these routes for this Windows device in https://login.tailscale.com/admin/machines'
    Write-Output 'Keep this PC running and disable sleep while plugged in. Existing advertised routes were preserved.'
    exit 0
}
# Certificate discovery only: no access codes are read and no MQTT login or command is sent.
if (-not ('RRPrinterProbe' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Net.Sockets;
using System.Net.Security;
using System.Security.Cryptography;
using System.Security.Authentication;
public static class RRPrinterProbe {
    public static string[] Read(string host) {
        bool connected = false;
        using (var client = new TcpClient()) {
            try {
                var task = client.ConnectAsync(host, 8883);
                if (!task.Wait(3000)) return new [] { "failed", "skipped", "" };
                task.GetAwaiter().GetResult(); connected = true;
                client.ReceiveTimeout = 3000; client.SendTimeout = 3000;
                using (var ssl = new SslStream(client.GetStream(), false, (s,c,ch,e) => true)) {
                    ssl.ReadTimeout = 3000; ssl.WriteTimeout = 3000;
                    ssl.AuthenticateAsClient(host, null, SslProtocols.Tls12, false);
                    using (var sha = SHA256.Create()) {
                        return new [] { "ok", "observed", BitConverter.ToString(sha.ComputeHash(ssl.RemoteCertificate.GetRawCertData())).Replace("-", "").ToLowerInvariant() };
                    }
                }
            } catch { return new [] { connected ? "ok" : "failed", connected ? "failed" : "skipped", "" }; }
        }
    }
}
'@
}
$checks = @($printers | ForEach-Object {
    $result = [RRPrinterProbe]::Read($_.ip)
    [ordered]@{ machine_no = [int]$_.machine_no; ip = $_.ip; credential_ref = $_.credential_ref; tcp = $result[0]; tls = $result[1]; observed_cert_sha256 = $result[2] }
})
$vpn = $null
if ($tailscale) {
    $status = & $tailscale status --json | ConvertFrom-Json
    $vpn = @{ state = $status.BackendState; ip = @($status.Self.TailscaleIPs); hostname = $status.Self.HostName }
}
$report = [ordered]@{
    observed_at = (Get-Date).ToUniversalTime().ToString('o'); computer = $env:COMPUTERNAME
    purpose = 'onsite_discovery_no_mqtt_login'; tailscale = $vpn
    adapters = @(Get-NetIPConfiguration | ForEach-Object { @{ name = $_.InterfaceAlias; ipv4 = @($_.IPv4Address | Select-Object IPAddress,PrefixLength); gateway = @($_.IPv4DefaultGateway.NextHop) } })
    printers = $checks
}
if ($IncludeGatewayDiagnostics) { $report.gateway_diagnostics = Read-GatewayDiagnostics }
$output = Join-Path $OutputDirectory "site-$stamp.json"
[IO.File]::WriteAllText($output, ($report | ConvertTo-Json -Depth 8), $utf8)
$checks | ForEach-Object { [pscustomobject]$_ } | Format-Table machine_no,ip,tcp,tls
Write-Output "Report: $output"
Write-Output 'Certificate hashes are observed onsite, not proof of machine identity. Match each IP with the physical printer.'
