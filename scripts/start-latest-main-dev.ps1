[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$ReplaceStale
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$viteScript = Join-Path $projectRoot 'node_modules\vite\bin\vite.js'

function Invoke-ProjectGit {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = & git -C $projectRoot @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($Arguments -join ' ')"
    }

    return ($output | Out-String).Trim()
}

function Get-ListenerOwner {
    $listener = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if (-not $listener) {
        return $null
    }

    return Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
}

function Test-ProjectViteProcess {
    param([Parameter(Mandatory = $true)]$Process)

    return $Process.CommandLine -and
        $Process.CommandLine.IndexOf($viteScript, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
}

function Wait-ForPortRelease {
    for ($attempt = 0; $attempt -lt 20; $attempt += 1) {
        if (-not (Get-ListenerOwner)) {
            return
        }

        Start-Sleep -Milliseconds 250
    }

    throw 'Port 5173 was not released within 5 seconds.'
}

function Wait-ForExpectedVite {
    for ($attempt = 0; $attempt -lt 20; $attempt += 1) {
        $owner = Get-ListenerOwner
        if ($owner -and (Test-ProjectViteProcess -Process $owner)) {
            return $owner
        }

        Start-Sleep -Milliseconds 250
    }

    throw 'Expected Vite server did not listen on port 5173 within 5 seconds.'
}

if (-not (Test-Path $viteScript)) {
    throw "Vite dependency is missing in this worktree: $viteScript. Run npm ci here first."
}

Invoke-ProjectGit -Arguments @('fetch', 'origin', 'main', '--prune') | Out-Null

$branch = Invoke-ProjectGit -Arguments @('branch', '--show-current')
if (-not $branch) {
    throw 'Detached HEAD is not allowed. Switch to a branch based on the latest main first.'
}

$head = Invoke-ProjectGit -Arguments @('rev-parse', '--short', 'HEAD')
$remoteMain = Invoke-ProjectGit -Arguments @('rev-parse', '--short', 'origin/main')
$distanceParts = (Invoke-ProjectGit -Arguments @('rev-list', '--left-right', '--count', 'HEAD...origin/main')) -split '\s+'
if ($distanceParts.Count -ne 2) {
    throw 'Unable to parse the commit distance from origin/main.'
}

$ahead = [int]$distanceParts[0]
$behind = [int]$distanceParts[1]
if ($behind -ne 0) {
    throw "Branch $branch is $behind commit(s) behind origin/main (HEAD $head, origin/main $remoteMain). Refusing to start stale code on port 5173."
}

$dirtyPaths = Invoke-ProjectGit -Arguments @('status', '--porcelain')
if ($dirtyPaths) {
    throw "This worktree has uncommitted changes. Commit, stash, or restore them before starting:`n$dirtyPaths"
}

$owner = Get-ListenerOwner
if ($owner) {
    if (Test-ProjectViteProcess -Process $owner) {
        Write-Host "Port 5173 is already served by this worktree (PID $($owner.ProcessId), branch $branch, HEAD $head, ahead of main by $ahead commit(s))."
        return
    }

    $staleSource = $owner.CommandLine
    if ($Check) {
        throw "Port 5173 is occupied by another worktree (PID $($owner.ProcessId)): $staleSource"
    }
    if (-not $ReplaceStale) {
        throw "Port 5173 is occupied by another worktree (PID $($owner.ProcessId)). It was not stopped automatically. Re-run with -ReplaceStale after confirming: $staleSource"
    }

    Stop-Process -Id $owner.ProcessId -Force
    Wait-ForPortRelease
}

if ($Check) {
    Write-Host "Startup check passed: branch $branch, HEAD $head, origin/main $remoteMain, behind 0 commit(s); port 5173 is safe to use."
    return
}

$node = (Get-Command node.exe -ErrorAction Stop).Source
$runtimeLogDirectory = Join-Path ([System.IO.Path]::GetTempPath()) 'royal-regent-nexus-dev'
New-Item -ItemType Directory -Force -Path $runtimeLogDirectory | Out-Null
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stdout = Join-Path $runtimeLogDirectory "vite-5173-$timestamp.stdout.log"
$stderr = Join-Path $runtimeLogDirectory "vite-5173-$timestamp.stderr.log"

$startInfo = @{
    FilePath = $node
    ArgumentList = @($viteScript, '--host', '127.0.0.1', '--port', '5173', '--strictPort')
    WorkingDirectory = $projectRoot
    WindowStyle = 'Hidden'
    RedirectStandardOutput = $stdout
    RedirectStandardError = $stderr
    PassThru = $true
}
$viteProcess = Start-Process @startInfo

$startedOwner = Wait-ForExpectedVite
Write-Host "Started Vite from this worktree (PID $($startedOwner.ProcessId), branch $branch, HEAD $head, ahead of main by $ahead commit(s))."
Write-Host "URL: http://127.0.0.1:5173"
Write-Host "Runtime log: $stdout"
