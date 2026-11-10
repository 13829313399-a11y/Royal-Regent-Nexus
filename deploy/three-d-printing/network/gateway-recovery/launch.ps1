param([switch]$Remove)
$ErrorActionPreference='Stop'
$entry=Join-Path $PSScriptRoot 'install-windows.ps1'
$argsText='-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$entry+'"'
if($Remove){$argsText+=' -Remove'}
$p=Start-Process -FilePath 'powershell.exe' -ArgumentList $argsText -Verb RunAs -WindowStyle Hidden -Wait -PassThru
Write-Host 'Send the guard-install JSON receipt from this folder.'
exit $p.ExitCode
