[CmdletBinding()]
param(
    [ValidateSet('Plan','Apply','Rollback')][string]$Action = 'Plan',
    [Parameter(Mandatory=$true)][string]$PrinterFile,
    [Parameter(Mandatory=$true)][string]$ExpectedGatewayIP,
    [string]$OutputDirectory,
    [string]$RestoreFile,
    [string]$TailscalePath
)
$ErrorActionPreference = 'Stop'
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $OutputDirectory) { $OutputDirectory=Join-Path $scriptDirectory 'reports' }
$utf8=[Text.UTF8Encoding]::new($false)
function Invoke-Tail([string[]]$Arguments) {
    $value=& $TailscalePath @Arguments 2>$null | Out-String
    if ($LASTEXITCODE -ne 0) { throw 'tailscale_command_failed' }
    return $value
}
function Read-Routes {
    $prefs=Invoke-Tail @('debug','prefs') | ConvertFrom-Json
    if ($null -eq $prefs.PSObject.Properties['AdvertiseRoutes']) { throw 'route_preferences_missing' }
    return @($prefs.AdvertiseRoutes | Where-Object { $_ } | Sort-Object -Unique)
}
$report=$null; $reportPath=$null
try {
    $rows=@(Import-Csv -LiteralPath $PrinterFile)
    if ($rows.Count -lt 1 -or $rows.Count -gt 16) { throw 'invalid_inventory' }
    $requested=@(); $numbers=@()
    foreach ($row in $rows) {
        $ip=[Net.IPAddress]::Parse($row.ip); $bytes=$ip.GetAddressBytes()
        if ($bytes.Length -ne 4 -or $ip.ToString() -cne $row.ip -or
            -not ($bytes[0] -eq 10 -or ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or ($bytes[0] -eq 192 -and $bytes[1] -eq 168))) { throw 'invalid_private_ipv4' }
        $number=[int]$row.machine_no
        $route=$ip.ToString()+'/32'
        if ($number -lt 1 -or $number -gt 16 -or $number -in $numbers -or $route -in $requested) { throw 'duplicate_or_invalid_inventory' }
        $numbers+=$number; $requested+=$route
    }
    $requested=@($requested | Sort-Object -Unique)
    if (-not $TailscalePath) {
        $command=Get-Command tailscale.exe -ErrorAction SilentlyContinue
        $TailscalePath=if($command){$command.Source}else{Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'}
    }
    if (-not (Test-Path -LiteralPath $TailscalePath -PathType Leaf)) { throw 'tailscale_not_installed' }
    $status=Invoke-Tail @('status','--json') | ConvertFrom-Json
    if ($status.BackendState -ne 'Running' -or $ExpectedGatewayIP -notin @($status.TailscaleIPs)) { throw 'wrong_gateway_or_not_logged_in' }
    $before=@(Read-Routes)
    $added=@($requested | Where-Object { $_ -notin $before })
    $removed=@()
    $desired=@(@($before)+@($requested) | Sort-Object -Unique)
    if ($Action -eq 'Rollback') {
        if (-not $RestoreFile) { throw 'restore_report_required' }
        $restore=Get-Content -LiteralPath $RestoreFile -Raw | ConvertFrom-Json
        if ($restore.action -ne 'Apply' -or $restore.gateway_ip -ne $ExpectedGatewayIP -or
            @($restore.added_routes | Where-Object { $_ -notin $requested }).Count -gt 0) { throw 'restore_report_scope_mismatch' }
        # Remove only routes that this specific application added. Retain all
        # other current routes, including those added after the application.
        $removed=@($before | Where-Object { $_ -in @($restore.added_routes) })
        $added=@()
        $desired=@($before | Where-Object { $_ -notin $removed })
    }
    $run=Join-Path $OutputDirectory ((Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8))
    New-Item -ItemType Directory -Path $run | Out-Null
    $reportPath=Join-Path $run 'route-change.json'
    $report=[ordered]@{version=1;action=$Action;gateway_ip=$ExpectedGatewayIP;observed_at=(Get-Date).ToUniversalTime().ToString('o');status='plan_only';before_routes=$before;requested_routes=$requested;added_routes=$added;removed_routes=$removed;desired_routes=$desired;after_routes=$before;mutation_attempted=$false;cloud_routes_verified=$false;mqtt_authenticated=$false;issue_code=''}
    [IO.File]::WriteAllText($reportPath,($report | ConvertTo-Json -Depth 6),$utf8)
    if ($Action -ne 'Plan' -and (($before -join ',') -cne ($desired -join ','))) {
        $current=@(Read-Routes)
        if (($current -join ',') -cne ($before -join ',')) { throw 'routes_changed_during_preparation' }
        # Persist the complete before/desired snapshot before requesting a change.
        $report.mutation_attempted=$true; $report.status='applying'
        [IO.File]::WriteAllText($reportPath,($report | ConvertTo-Json -Depth 6),$utf8)
        Invoke-Tail @('set',('--advertise-routes='+($desired -join ','))) | Out-Null
        $report.after_routes=@(Read-Routes)
        if (($report.after_routes -join ',') -cne ($desired -join ',')) { throw 'route_readback_mismatch' }
        $report.status=if($Action -eq 'Rollback'){'added_routes_removed'}else{'advertised_pending_cloud_verification'}
    } elseif ($Action -ne 'Plan') { $report.status='already_in_requested_state' }
    [IO.File]::WriteAllText($reportPath,($report | ConvertTo-Json -Depth 6),$utf8)
    Write-Output ('Status: '+$report.status)
    Write-Output ('Added routes: '+$added.Count+'; removed routes: '+$removed.Count)
    Write-Output ('Report: '+$reportPath)
    if ($Action -eq 'Apply') { Write-Output 'Route advertisement does not prove cloud access. New routes may require approval in the Tailscale admin console.' }
} catch {
    $code=$_.Exception.Message
    if ($code -notmatch '^[a-z_]+$') { $code='route_update_failed' }
    if ($report -and $reportPath) {
        $report.status='failed'; $report.issue_code=$code
        [IO.File]::WriteAllText($reportPath,($report | ConvertTo-Json -Depth 6),$utf8)
        Write-Output ('Report: '+$reportPath)
    }
    [Console]::Error.WriteLine('Route operation stopped: '+$code)
    exit 1
}
