param([switch]$Remove)
$ErrorActionPreference='Stop'
$root=Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'RRNexus-3D-GatewayGuard'
$taskName='RRNexus-3D-GatewayGuard'
$ps=[IO.Path]::GetFullPath((Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'))
$receipt=Join-Path $PSScriptRoot ('guard-install-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'-'+$PID+'.json')
$note=[ordered]@{at=[DateTime]::UtcNow.ToString('o');result='checking';task_registered=$false;system_sample=$null;field_checks=$null;issue=$null}
function Assert-Plain($path) {
    if((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'unexpected_reparse_point'}
}
function Ensure-ProtectedDirectory($path) {
    $admins=[Security.Principal.SecurityIdentifier]::new('S-1-5-32-544');$system=[Security.Principal.SecurityIdentifier]::new('S-1-5-18')
    if(!(Test-Path -LiteralPath $path)){
        $acl=[Security.AccessControl.DirectorySecurity]::new();$acl.SetAccessRuleProtection($true,$false);$acl.SetOwner($admins)
        foreach($sid in @($admins,$system)){
            $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow'))
        }
        [void][IO.Directory]::CreateDirectory($path,$acl)
    }
    Assert-Plain $path
    $acl=Get-Acl -LiteralPath $path
    if(!$acl.AreAccessRulesProtected -or $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin @($admins.Value,$system.Value)){throw 'untrusted_install_directory'}
    foreach($ace in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
        if($ace.AccessControlType -eq 'Allow' -and $ace.IdentityReference.Value -notin @($admins.Value,$system.Value)){throw 'untrusted_install_permissions'}
    }
}
function Assert-OwnedTask($task) {
    if(!$task){return}
    $actions=@($task.Actions)
    $principal=[string]$task.Principal.UserId
    if($principal -ne 'S-1-5-18'){try{$principal=([Security.Principal.NTAccount]::new($principal)).Translate([Security.Principal.SecurityIdentifier]).Value}catch{throw 'unexpected_task_principal'}}
    if($actions.Count -ne 1 -or [IO.Path]::GetFullPath($actions[0].Execute) -ine $ps -or $actions[0].Arguments -notmatch ('-File "'+[regex]::Escape($root)+'\\payload-[0-9a-f]{16}\\guard\.ps1"$') -or $principal -ne 'S-1-5-18'){throw 'conflicting_existing_task'}
}
try {
    $cfg=Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'site.json')|ConvertFrom-Json
    if($env:COMPUTERNAME -ine $cfg.hostname){throw 'run_on_factory_3D'}
    $identity=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if(!$identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'administrator_required'}
    $task=Get-ScheduledTask -TaskPath '\' -TaskName $taskName -ErrorAction SilentlyContinue
    Assert-OwnedTask $task
    if($Remove){
        if($task){Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue;Unregister-ScheduledTask -TaskName $taskName -Confirm:$false}
        $note.result='removed';return
    }
    . (Join-Path $PSScriptRoot 'windows-network.ps1')
    $script:vpnExe=Join-Path $env:ProgramFiles 'Tailscale/tailscale.exe'
    [void](Read-SiteVpn $cfg);[void](Get-Binding)
    Ensure-ProtectedDirectory $root
    $manifestFile=Join-Path $PSScriptRoot 'manifest.json'
    $manifest=Get-Content -Raw -LiteralPath $manifestFile|ConvertFrom-Json
    $tag=(Get-FileHash -LiteralPath $manifestFile -Algorithm SHA256).Hash.ToLowerInvariant().Substring(0,16)
    $payload=Join-Path $root ('payload-'+$tag);Ensure-ProtectedDirectory $payload
    $files=@('guard.ps1','windows-network.ps1','RRFleetStatus.cs','RRLinkAddress.cs','RRWiredProbe.cs','RRTcpSession.cs','site.json')
    foreach($name in $files){
        $from=Join-Path $PSScriptRoot $name;$to=Join-Path $payload $name;$expected=$manifest.$name
        if(!$expected -or (Get-FileHash -LiteralPath $from -Algorithm SHA256).Hash -ine $expected){throw 'damaged_installer'}
        if(!(Test-Path -LiteralPath $to)){
            $bytes=[IO.File]::ReadAllBytes($from);$out=[IO.File]::Open($to,'CreateNew','Write','None')
            try{$out.Write($bytes,0,$bytes.Length)}finally{$out.Dispose()}
            $a=Get-Acl -LiteralPath $to;$a.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'));Set-Acl -LiteralPath $to -AclObject $a
        }
        Assert-Plain $to
        $rights=Get-Acl -LiteralPath $to
        if($rights.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-32-544','S-1-5-18')){throw 'untrusted_payload_owner'}
        foreach($ace in $rights.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
            if($ace.AccessControlType -eq 'Allow' -and $ace.IdentityReference.Value -notin @('S-1-5-32-544','S-1-5-18')){throw 'untrusted_payload_permissions'}
        }
        if((Get-FileHash -LiteralPath $to -Algorithm SHA256).Hash -ine $expected){throw 'installed_payload_mismatch'}
    }
    $entry=Join-Path $payload 'guard.ps1'
    $argsText='-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+$entry+'"'
    $previous=if($task){Export-ScheduledTask -TaskName $taskName -TaskPath '\'}else{$null}
    try{
        $action=New-ScheduledTaskAction -Execute $ps -Argument $argsText
        $minute=New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes 1)
        $boot=New-ScheduledTaskTrigger -AtStartup
        $principal=New-ScheduledTaskPrincipal -UserId 'S-1-5-18' -LogonType ServiceAccount -RunLevel Highest
        $settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
        Register-ScheduledTask -TaskName $taskName -TaskPath '\' -Action $action -Trigger @($boot,$minute) -Principal $principal -Settings $settings -Force|Out-Null
        $note.task_registered=$true
        $now=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        Start-ScheduledTask -TaskName $taskName
        $last=Join-Path $root 'last-check.json'
        for($i=0;$i -lt 75;$i++){
            Start-Sleep -Seconds 2
            if(Test-Path -LiteralPath $last){$q=Get-Content -Raw -LiteralPath $last|ConvertFrom-Json;if($q.at -ge $now -and $q.system -and $q.payload -ceq ('payload-'+$tag)){$note.system_sample=$q;break}}
        }
        $check=Get-ScheduledTask -TaskName $taskName -TaskPath '\';Assert-OwnedTask $check
        if(!$check.Settings.Enabled -or @($check.Triggers).Count -ne 2){throw 'persistent_task_not_verified'}
        if(!$note.system_sample){throw 'system_task_no_first_receipt'}
        $note.result=if($note.system_sample.result -in @('sampled','already_sampled')){'installed_and_paired'}else{'installed_waiting_for_valid_evidence'}
    }catch{
        if($note.task_registered){Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            if($previous){Register-ScheduledTask -TaskName $taskName -TaskPath '\' -Xml $previous -Force|Out-Null}
            else{Unregister-ScheduledTask -TaskName $taskName -Confirm:$false};$note.task_registered=[bool]$previous}
        throw
    }
    # The installation receipt remains valid even if a separate read-only diagnostic fails.
    try {
        . $entry -FunctionsOnly
        foreach($native in @('RRFleetStatus','RRLinkAddress','RRWiredProbe')){
            Add-Type -Path (Join-Path $payload ($native+'.cs'))
        }
        $note.field_checks=Get-InstallDiagnostics $cfg
    } catch { $note.field_checks=[ordered]@{issue=$_.Exception.GetBaseException().Message} }
} catch {$note.result='incomplete';$note.issue=$_.Exception.GetBaseException().Message}
finally {[IO.File]::WriteAllText($receipt,($note|ConvertTo-Json -Depth 7),[Text.UTF8Encoding]::new($false));Write-Host ('Receipt: '+$receipt)}
if($note.result -eq 'incomplete'){exit 1}
