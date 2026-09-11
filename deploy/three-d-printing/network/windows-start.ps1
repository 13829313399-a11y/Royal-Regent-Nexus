$ErrorActionPreference = 'Stop'
$siteDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host 'RR 3D - Windows site setup'
Write-Host '1. Check printer LAN + collect TLS certificate hashes'
Write-Host '2. Install Tailscale'
Write-Host '3. Log in to Tailscale (same account as cloud)'
Write-Host '4. Advertise printer routes'
Write-Host '5. Open the cloud 3D page'
$choice = Read-Host 'Choose 1-5'
if ($choice -eq '5') {
    Start-Process 'http://47.115.217.27/modules/production/three-d-printing?factory=huakang-a'
} else {
    $actions = @{ '1'='Inspect'; '2'='Install'; '3'='Login'; '4'='Routes' }
    if (-not $actions.ContainsKey($choice)) { throw 'Choose 1-5.' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $siteDirectory 'windows-site.ps1') -Action $actions[$choice] -PrinterFile (Join-Path $siteDirectory 'printers.csv') -OutputDirectory (Join-Path $siteDirectory 'reports')
    if ($LASTEXITCODE -ne 0) { throw 'The selected step failed. Read the error above before retrying.' }
}
Read-Host 'Press Enter to close'
