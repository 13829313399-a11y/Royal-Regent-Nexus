param(
  [Parameter(Mandatory=$true)][string]$Executable,
  [Parameter(Mandatory=$true)][string]$ConfigPath,
  [string]$InstallDir = 'C:\ProgramData\RoyalRegent\UVAgent'
)
$ErrorActionPreference = 'Stop'
$exeSource = (Resolve-Path -LiteralPath $Executable).Path
$configSource = (Resolve-Path -LiteralPath $ConfigPath).Path
$target = [IO.Path]::GetFullPath($InstallDir)
if (-not $target.StartsWith('C:\ProgramData\RoyalRegent\UVAgent', [StringComparison]::OrdinalIgnoreCase)) { throw 'Use the dedicated UVAgent installation directory.' }
if (Get-Service -Name RRUvAgent -ErrorAction SilentlyContinue) { throw 'Service already exists. Stop it and follow the upgrade runbook; existing queue must be retained.' }
New-Item -ItemType Directory -Force -Path $target,(Join-Path $target 'state') | Out-Null
Copy-Item -LiteralPath $exeSource -Destination (Join-Path $target 'rr-uv-agent.exe')
Copy-Item -LiteralPath $configSource -Destination (Join-Path $target 'config.toml')
New-Item -Path 'HKLM:\SOFTWARE\RoyalRegent\UVAgent' -Force | Out-Null
Set-ItemProperty -Path 'HKLM:\SOFTWARE\RoyalRegent\UVAgent' -Name ConfigPath -Value (Join-Path $target 'config.toml')
& sc.exe create RRUvAgent binPath= ('"' + (Join-Path $target 'rr-uv-agent.exe') + '"') obj= 'NT AUTHORITY\LocalService' start= delayed-auto DisplayName= 'Royal Regent UV Read-only Agent'
if ($LASTEXITCODE -ne 0) { throw 'Service registration failed.' }
& sc.exe sidtype RRUvAgent unrestricted
& icacls.exe $target /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' 'NT SERVICE\RRUvAgent:(OI)(CI)RX'
& icacls.exe (Join-Path $target 'state') /grant:r 'NT SERVICE\RRUvAgent:(OI)(CI)M'
& sc.exe failure RRUvAgent reset= 86400 actions= restart/10000/restart/30000/restart/60000
Write-Output 'Installed, not started. Pair with --config <config.toml> enroll; grant read access only to approved log directories, then Start-Service RRUvAgent.'
