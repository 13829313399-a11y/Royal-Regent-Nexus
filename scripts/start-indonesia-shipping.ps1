param(
  [Parameter(Mandatory=$true)][ValidateSet('huakang-a','huakang-b','huakang-c','huakang-d','huadeng','huaxing')][string]$Factory,
  [string]$Dotnet = 'dotnet',
  [int]$Port = 5180,
  [switch]$Build
)
$ErrorActionPreference = 'Stop'
# Secrets are inherited from this shell, never written to a tracked file.
if (-not $env:INDONESIA_SHIPPING_CONNECTION_STRING -or -not $env:INDONESIA_SHIPPING_BRIDGE_KEY) {
  throw 'Set INDONESIA_SHIPPING_CONNECTION_STRING and INDONESIA_SHIPPING_BRIDGE_KEY in this shell first.'
}
$taskRoot = Split-Path -Parent $PSScriptRoot
$serviceRoot = Join-Path $taskRoot 'services/indonesia-shipping'
$publishRoot = Join-Path $serviceRoot 'publish'
if ($Build) {
  Push-Location (Join-Path $serviceRoot 'web')
  try {
    $env:VITE_BASE_PATH = './'
    & npm.cmd ci
    if ($LASTEXITCODE) { throw 'Indonesia frontend dependency installation failed' }
    & npm.cmd run build
    if ($LASTEXITCODE) { throw 'Indonesia frontend build failed' }
  } finally { Pop-Location }
  & $Dotnet publish (Join-Path $serviceRoot 'src/IndoShipping.Api/IndoShipping.Api.csproj') -c Release -o $publishRoot
  if ($LASTEXITCODE) { throw 'Indonesia API publish failed' }
  New-Item -ItemType Directory -Path (Join-Path $publishRoot 'wwwroot') -Force | Out-Null
  Copy-Item -Path (Join-Path $serviceRoot 'web/dist/*') -Destination (Join-Path $publishRoot 'wwwroot') -Recurse -Force
}
if (-not (Test-Path -LiteralPath (Join-Path $publishRoot 'IndoShipping.Api.dll'))) { throw 'Build first with -Build' }
$env:NexusBridge__Enabled = 'true'
$env:NexusBridge__FactoryId = $Factory
$env:NexusBridge__Key = $env:INDONESIA_SHIPPING_BRIDGE_KEY
$env:ConnectionStrings__Default = $env:INDONESIA_SHIPPING_CONNECTION_STRING
$env:ASPNETCORE_URLS = "http://127.0.0.1:$Port"
Push-Location $publishRoot
try { & $Dotnet (Join-Path $publishRoot 'IndoShipping.Api.dll') } finally { Pop-Location }
