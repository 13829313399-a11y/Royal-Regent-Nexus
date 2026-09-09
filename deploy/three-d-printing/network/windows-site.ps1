[CmdletBinding()]
param(
    [ValidateSet('Inspect','Install','Login','Routes')][string]$Action = 'Inspect',
    [string]$PrinterFile,
    [string]$OutputDirectory
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
    if ($rows.Count -eq 0) { throw 'Fill printers.csv with machine_no and ip first.' }
    $numbers = @(); $addresses = @()
    foreach ($row in $rows) {
        $ip = [Net.IPAddress]::Parse($row.ip)
        $b = $ip.GetAddressBytes()
        if ($b.Length -ne 4 -or -not ($b[0] -eq 10 -or ($b[0] -eq 172 -and $b[1] -ge 16 -and $b[1] -le 31) -or ($b[0] -eq 192 -and $b[1] -eq 168))) { throw 'Use the printer LAN IPv4 address.' }
        $number = [int]$row.machine_no
        if ($number -lt 1 -or $number -gt 11 -or $numbers -contains $number -or $addresses -contains $ip.ToString()) { throw 'Duplicate or invalid printer number/address.' }
        $numbers += $number; $addresses += $ip.ToString()
    }
    return $rows
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
    [ordered]@{ machine_no = [int]$_.machine_no; ip = $_.ip; tcp = $result[0]; tls = $result[1]; observed_cert_sha256 = $result[2] }
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
$output = Join-Path $OutputDirectory "site-$stamp.json"
[IO.File]::WriteAllText($output, ($report | ConvertTo-Json -Depth 8), $utf8)
$checks | ForEach-Object { [pscustomobject]$_ } | Format-Table machine_no,ip,tcp,tls
Write-Output "Report: $output"
Write-Output 'Certificate hashes are observed onsite, not proof of machine identity. Match each IP with the physical printer.'
