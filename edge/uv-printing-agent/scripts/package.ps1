param([string]$Python = 'python', [string]$OutputDir = 'dist')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Push-Location $root
try {
  & $Python -m PyInstaller --noconfirm --onefile --name rr-uv-agent --paths src --hidden-import win32timezone --hidden-import apsw --distpath $OutputDir src/uv_agent/windows_service.py
  if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
  Copy-Item -LiteralPath config.example.toml,README.md -Destination $OutputDir
  Copy-Item -LiteralPath scripts/install.ps1,scripts/uninstall.ps1 -Destination $OutputDir
  Get-FileHash -LiteralPath (Join-Path $OutputDir 'rr-uv-agent.exe') -Algorithm SHA256 | Format-List
} finally { Pop-Location }
