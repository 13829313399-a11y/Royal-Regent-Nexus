$ErrorActionPreference = 'Stop'
$service = Get-Service -Name RRUvAgent -ErrorAction SilentlyContinue
if ($service) {
  if ($service.Status -ne 'Stopped') { Stop-Service -Name RRUvAgent }
  & sc.exe delete RRUvAgent
  if ($LASTEXITCODE -ne 0) { throw 'Service removal failed.' }
}
Write-Output 'Service removed. Configuration, protected identity, outbox and logs are retained for recovery.'
