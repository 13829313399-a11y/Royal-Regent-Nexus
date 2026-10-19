[CmdletBinding()]
param(
    [ValidateSet('Start', 'Status', 'Stop')][string]$Action = 'Start',
    [string]$Python,
    [ValidateRange(1024, 65535)][int]$ApiPort = 8000,
    [ValidateRange(1024, 65535)][int]$FrontendPort = 5173,
    [string]$RuntimeDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendRoot = Join-Path $projectRoot 'backend'
$viteScript = Join-Path $projectRoot 'node_modules\vite\bin\vite.js'
if ($ApiPort -eq $FrontendPort) { throw 'API and frontend must use different ports.' }
if (-not $RuntimeDirectory) { $RuntimeDirectory = Join-Path $projectRoot '.local-dev' }
$runtimeRoot = [IO.Path]::GetFullPath($RuntimeDirectory)
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
$statePath = Join-Path $runtimeRoot 'state.json'
# Serialize start/stop invocations. SQLite's worker lock remains authoritative.
$lock = [IO.File]::Open((Join-Path $runtimeRoot 'launcher.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
$services = @{}

function Get-ProcessRecord([int]$ProcessId) {
    Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId"
}

function Test-TrackedProcess($Record) {
    if (-not $Record) { return $false }
    $process = Get-ProcessRecord $Record.ProcessId
    return $process -and $process.CommandLine -ceq $Record.CommandLine -and
        [string]$process.CreationDate.ToUniversalTime().Ticks -eq $Record.CreatedAtTicks
}

function Save-State {
    $state = @{ ProjectRoot = $projectRoot; ApiPort = $ApiPort; FrontendPort = $FrontendPort; Services = $services }
    $temporary = Join-Path $runtimeRoot 'state.json.tmp'
    [IO.File]::WriteAllText($temporary, ($state | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $statePath -Force
}

function Get-Listener([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { Get-ProcessRecord $listener.OwningProcess }
}

function Test-Api {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 2
        return $response.status -eq 'ok' -and $response.service -eq 'Royal Regent Nexus API'
    } catch { return $false }
}

function Test-Frontend {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$FrontendPort/@vite/client" -TimeoutSec 2
        return $response.StatusCode -eq 200 -and $response.Content -match 'vite'
    } catch { return $false }
}

function Get-Worker {
    $heartbeatRoot = Join-Path $backendConfig.storage 'heartbeats'
    if (-not (Test-Path -LiteralPath $heartbeatRoot)) { return $null }
    $cutoff = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - 25
    foreach ($file in Get-ChildItem -LiteralPath $heartbeatRoot -Filter '*.json') {
        try {
            $heartbeat = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($heartbeat.timestamp -lt $cutoff -or $heartbeat.host -ine [Environment]::MachineName) { continue }
            $heartbeatProcessId = [int]$heartbeat.pid
            if ($heartbeatProcessId -lt 1) { continue }
        } catch { continue }
        $process = Get-ProcessRecord $heartbeatProcessId
        if ($process -and $process.CommandLine -match '-m\s+app\.workers\.document_tools(?:\s|$)') {
            return $process
        }
    }
    return $null
}

function ConvertTo-NativeArgument([string]$Value) {
    # Start-Process joins ArgumentList; quote for Windows argv, never for a shell.
    if ($Value -and $Value -notmatch '[\s"]') { return $Value }
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Start-ServiceProcess([string]$Name, [string]$Executable, [string[]]$Arguments, [string]$Directory) {
    $stamp = [DateTime]::Now.ToString('yyyyMMdd-HHmmss-fff')
    $stdout = Join-Path $runtimeRoot "$Name-$stamp.stdout.log"
    $stderr = Join-Path $runtimeRoot "$Name-$stamp.stderr.log"
    $argumentLine = ($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '
    $process = Start-Process -FilePath $Executable -ArgumentList $argumentLine -WorkingDirectory $Directory `
        -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $identity = Get-ProcessRecord $process.Id
    if (-not $identity) { throw "$Name exited on startup. See $stderr" }
    $services[$Name] = @{
        ProcessId = $identity.ProcessId; CreatedAtTicks = [string]$identity.CreationDate.ToUniversalTime().Ticks
        CommandLine = $identity.CommandLine; Stdout = $stdout; Stderr = $stderr
    }
    Save-State
    Write-Host "Started $Name (PID $($process.Id)). Log: $stderr"
    return $process
}

function Wait-Ready([string]$Name, $Process, [scriptblock]$Probe, [int]$Seconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        $Process.Refresh()
        if ($Process.HasExited) { throw "$Name exited before becoming ready. See $($services[$Name].Stderr)" }
        if (& $Probe) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not become ready within $Seconds seconds. See $($services[$Name].Stderr)"
}

try {
    if (Test-Path -LiteralPath $statePath) {
        $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($state.ProjectRoot -ine $projectRoot) { throw 'Runtime state belongs to another checkout.' }
        if ($state.ApiPort -ne $ApiPort -or $state.FrontendPort -ne $FrontendPort) {
            throw 'Runtime state uses different ports. Use its original ports or a separate -RuntimeDirectory.'
        }
        foreach ($property in $state.Services.PSObject.Properties) { $services[$property.Name] = $property.Value }
    }

    if ($Action -eq 'Stop') {
        foreach ($name in @('worker', 'api', 'frontend')) {
            if (-not $services.ContainsKey($name)) { continue }
            $record = $services[$name]
            # A reused PID must never allow us to stop an unrelated application.
            if (Test-TrackedProcess $record) {
                & taskkill.exe /PID $record.ProcessId /T /F | Out-Null
                if ($LASTEXITCODE -ne 0) { throw "Unable to stop $name (PID $($record.ProcessId))." }
                Write-Host "Stopped $name (PID $($record.ProcessId))."
            }
            $services.Remove($name)
        }
        Save-State
        Write-Host 'Stopped launcher-owned processes. Pre-existing services were left running.'
        return
    }

    if (-not $Python) {
        $candidates = @(
            (Join-Path $backendRoot '.venv312\Scripts\python.exe'),
            (Join-Path $backendRoot '.venv\Scripts\python.exe'),
            (Join-Path (Split-Path $projectRoot -Parent) 'Royal-Regent-Nexus\backend\.venv312\Scripts\python.exe')
        )
        $Python = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $Python -or -not (Test-Path -LiteralPath $Python)) { throw 'Pass -Python with the backend virtual environment python.exe path.' }
    $Python = (Resolve-Path -LiteralPath $Python).Path
    if (-not (Test-Path -LiteralPath (Join-Path $backendRoot '.env'))) {
        throw 'Configure backend/.env with the existing database and private storage paths first.'
    }
    # Read only configuration, without importing the API or initializing a database.
    $probe = @'
import json
from pathlib import Path
from sqlalchemy.engine import make_url
from app.core.config import settings
url = make_url(settings.database_url)
print(json.dumps(dict(storage=str(Path(settings.document_tools_storage_dir).resolve()),
    enabled=settings.document_tools_enabled, environment=settings.app_env,
    database_exists=url.get_backend_name() != 'sqlite' or bool(url.database and Path(url.database).is_file()))))
'@
    Push-Location $backendRoot
    try {
        $configuration = & $Python -c $probe
        if ($LASTEXITCODE -ne 0) { throw 'Unable to load the backend configuration using this Python environment.' }
        $backendConfig = $configuration | ConvertFrom-Json
    } finally { Pop-Location }
    if ($backendConfig.environment -in @('prod', 'production')) { throw 'This launcher is for local development, not production.' }
    if (-not $backendConfig.database_exists) { throw 'Configured SQLite database is missing; refusing to create an empty replacement.' }
    if (-not $backendConfig.enabled) { throw 'DOCUMENT_TOOLS_ENABLED is disabled. The launcher does not change feature flags.' }

    $apiOwner = Get-Listener $ApiPort
    $frontendOwner = Get-Listener $FrontendPort
    $worker = Get-Worker
    $apiOnline = Test-Api
    $frontendOnline = Test-Frontend
    if ($Action -eq 'Status') {
        Write-Host "API: $apiOnline (http://127.0.0.1:$ApiPort/health)"
        Write-Host "Frontend: $frontendOnline (http://127.0.0.1:$FrontendPort)"
        Write-Host "Document worker: $([bool]$worker)"
        return
    }

    if ($apiOwner -and (-not $apiOnline -or $apiOwner.CommandLine -notmatch 'uvicorn\s+app\.main:app')) {
        throw "API port $ApiPort is occupied by an unexpected or unhealthy process (PID $($apiOwner.ProcessId)). It was not stopped."
    }
    if ($frontendOwner -and (-not $frontendOnline -or $frontendOwner.CommandLine -notmatch 'vite(?:\.js|[/\\]bin[/\\]vite\.js)')) {
        throw "Frontend port $FrontendPort is occupied by an unexpected or unhealthy process (PID $($frontendOwner.ProcessId)). It was not stopped."
    }
    if (-not (Test-Path -LiteralPath $viteScript)) { throw 'Vite is missing; install frontend dependencies in this checkout first.' }
    $node = (Get-Command node.exe -ErrorAction Stop).Source

    if (-not $apiOnline) {
        $process = Start-ServiceProcess 'api' $Python @('-m', 'uvicorn', 'app.main:app', '--app-dir', $backendRoot, '--host', '127.0.0.1', '--port', "$ApiPort") $backendRoot
        Wait-Ready 'api' $process { Test-Api } 45
    } else { Write-Host "Reusing healthy API (PID $($apiOwner.ProcessId))." }

    if (-not $worker) {
        $process = Start-ServiceProcess 'worker' $Python @('-m', 'app.workers.document_tools') $backendRoot
        Wait-Ready 'worker' $process { Get-Worker } 25
    } else { Write-Host "Reusing healthy document worker (PID $($worker.ProcessId))." }

    if (-not $frontendOnline) {
        $previousProxy = $env:VITE_API_PROXY_TARGET
        try {
            $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
            $process = Start-ServiceProcess 'frontend' $node @($viteScript, '--host', '127.0.0.1', '--port', "$FrontendPort", '--strictPort') $projectRoot
        } finally { $env:VITE_API_PROXY_TARGET = $previousProxy }
        Wait-Ready 'frontend' $process { Test-Frontend } 30
    } else { Write-Host "Reusing healthy frontend (PID $($frontendOwner.ProcessId))." }

    # Check all three together; never report success for only a healthy API.
    if (-not (Test-Api) -or -not (Test-Frontend) -or -not (Get-Worker)) {
        throw 'A local service became unhealthy during startup. Run -Action Status and inspect the logs.'
    }
    Write-Host "Local services ready: http://127.0.0.1:$FrontendPort (API $ApiPort + document worker)."
} finally { $lock.Dispose() }
