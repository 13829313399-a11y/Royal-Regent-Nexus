[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string[]]$PrinterIPs,
    [Parameter(Mandatory=$true)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
if ($PrinterIPs.Count -ne 11 -or ($PrinterIPs | Select-Object -Unique).Count -ne 11) {
    throw 'Exactly eleven distinct printer addresses are required.'
}
foreach ($address in $PrinterIPs) {
    $parsed = [System.Net.IPAddress]::Parse($address)
    if ($parsed.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork -or $parsed.ToString() -ne $address) { throw 'Canonical IPv4 required.' }
    $bytes = $parsed.GetAddressBytes()
    $privateAddress = $bytes[0] -eq 10 -or ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or ($bytes[0] -eq 192 -and $bytes[1] -eq 168)
    if (-not $privateAddress) { throw 'Printer addresses must be private IPv4 addresses.' }
}
if (Test-Path -LiteralPath $OutputPath) { throw 'Output already exists.' }
$routes = ($PrinterIPs | ForEach-Object { "$_/32" }) -join ','
$plan = [ordered]@{
    mode = 'plan_only_no_network_changes'
    factory_id = 'huakang-a'
    prerequisites = @('Company-managed Tailscale login', 'Confirm all printer IPs and fixed allocation', 'Review existing advertised routes before replacement', 'Tailnet policy restricts connector identity to printer IPs TCP 8883 only', 'Approve each advertised route in admin console', 'Enable unattended operation and verify after reboot', 'Retain existing Windows firewall; no public port mappings')
    reviewed_command = "tailscale set --advertise-routes=$routes"
    scope = 'Eleven host routes; does not expose the entire office subnet'
    rollback = 'Restore the previously recorded advertised routes and ACL; never clear unrelated company routes'
    source = 'https://tailscale.com/docs/features/subnet-routers/how-to/setup?tab=windows'
    field_acceptance = @('Cloud TCP and pinned TLS/MQTT', 'LAN remains usable', 'Unapproved tailnet identity denied', 'Cloud failure and Windows reboot recover', 'No public access to printer ports')
}
$json = $plan | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText([System.IO.Path]::GetFullPath($OutputPath), $json, [System.Text.UTF8Encoding]::new($false))
Write-Output 'Review plan written. No software installed and no routes, ACLs or firewall rules changed.'
