param([switch]$ObserveOnly,[switch]$FunctionsOnly)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'windows-network.ps1')

function Epoch { [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() }
function Write-AtomicJson($path,$value) {
    $tmp=$path+'.'+$PID+'.tmp'
    [IO.File]::WriteAllText($tmp,($value|ConvertTo-Json -Depth 9 -Compress),[Text.UTF8Encoding]::new($false))
    if([IO.File]::Exists($path)){[IO.File]::Replace($tmp,$path,[NullString]::Value)}else{[IO.File]::Move($tmp,$path)}
}
function New-GuardState {
    [pscustomobject]@{version=1;tick=0;snapshot=0;last_paired=0;last_majority=0;overlay_start=0;overlay_count=0;stopped_since=0;stopped_count=0;history=@();
        printers=@(foreach($n in 1..18){[pscustomobject]@{n=$n;good=0;since=0;votes=0;last_proof=0}})}
}
function Read-Health($config) {
    $d=[RRFleetStatus]::Read($config.cloud,$config.port,$config.pin,[string]$script:guardReceipt) | ConvertFrom-Json
    $age=(Epoch)-[long]$d.timestamp
    if($d.version -ne 1 -or $d.fleet -cne 'huakang-a/heyuan/18' -or $d.mapping -cne $config.mapping -or $age -lt -5 -or $age -gt 60){throw 'stale_or_unpaired_cloud_evidence'}
    if((@($d.printers.n) -join ',') -cne (1..18 -join ',')){throw 'incomplete_cloud_evidence'}
    if($d.collector_ok -isnot [bool] -or !$d.collector_ok -or $d.routes_ok -isnot [bool] -or !$d.routes_ok){throw 'cloud_or_routes_unhealthy'}
    foreach($p in $d.printers){
        if($p.fresh -isnot [bool] -or $p.silent -isnot [bool] -or $p.tcp_open -isnot [bool] -or ($p.fresh -and $p.silent)){throw 'invalid_printer_evidence'}
        if($null -ne $p.last_good_utc -and (($p.last_good_utc -isnot [long] -and $p.last_good_utc -isnot [int]) -or $p.last_good_utc -lt 0 -or $p.last_good_utc -gt $d.timestamp)){throw 'invalid_printer_history'}
    }
    return $d
}
function Clear-PrinterVotes($state) {foreach($p in $state.printers){$p.since=0;$p.votes=0;if($p.PSObject.Properties['last_proof']){$p.last_proof=0}}}
function Hold-AfterReadFailure($state,$reason,[long]$now) {
    # Missing transport grants no vote. Only a later, authenticated, unchanged
    # last device frame can bridge a short gap for an individual printer.
    if($reason -ne 'status_transport_unreachable' -or !$state.last_paired -or $now -lt $state.tick -or
       $now -lt $state.last_paired -or $now-$state.last_paired -gt 360){Clear-PrinterVotes $state}
    else{foreach($p in $state.printers){if(!$p.last_proof){$p.since=0;$p.votes=0}}}
    $state.last_majority=0
}
function Get-InstallDiagnostics($config) {
    $result=[ordered]@{at=Epoch;cloud_sample=$null;devices=@();issue=$null}
    try {
        $binding=Get-Binding
        $data=Read-Health $config
        $result.cloud_sample=$data.timestamp
        $service=$null;$connections=$null
        try {
            $service=Read-ServiceIdentity
            $connections=@(Get-NetTCPConnection -State Established -ErrorAction Stop | Where-Object RemotePort -eq 8883)
        } catch { $result.issue='gateway_socket_inventory_unavailable' }
        foreach($candidate in @($data.printers | Where-Object silent -eq $true)) {
            # Each probe uses current cloud evidence and the active physical LAN binding.
            if((Epoch)-$data.timestamp -gt 20){$data=Read-Health $config}
            $p=$data.printers[[int]$candidate.n-1]
            if(!$p.silent -or $p.fresh){continue}
            $device=$config.devices[[int]$p.n-1]
            $row=[ordered]@{n=$p.n;cloud_sample=$data.timestamp;last_good_utc=$p.last_good_utc;cloud_tcp=$p.tcp_open;
                mac='unverified';lan_tcp='not_tested';verified_gateway_sockets=$null}
            $result.devices+=@($row)
            if($null -ne $connections -and $null -ne $service){
                $row.verified_gateway_sockets=@(Read-Forwarders $device $binding $service $connections $result.at).Count
            }
            $link=Read-PrinterLink $device $binding
            if($link.code -ne 0 -or !$link.mac){$row.mac='unresolved';continue}
            if($link.mac -ine $device.mac){$row.mac='mismatch';continue}
            $row.mac='match'
            if($p.tcp_open){$row.lan_tcp='skipped_cloud_socket';continue}
            if((Epoch)-$data.timestamp -gt 30){$row.lan_tcp='skipped_stale_sample';continue}
            $tcp=Read-PrinterPort $device $binding
            if(!$tcp.interface_forced){$row.lan_tcp='binding_unverified'}
            elseif($tcp.status -eq 'ok'){$row.lan_tcp='reachable'}
            elseif($tcp.error -in @('TimedOut','timeout')){$row.lan_tcp='timeout'}
            elseif($tcp.error -eq 'ConnectionRefused'){$row.lan_tcp='refused'}
            else{$row.lan_tcp='unverified'}
        }
    } catch { $result.issue=$_.Exception.GetBaseException().Message }
    return $result
}
function Update-Evidence($state,$data,[long]$now) {
    $dt=$now-$state.tick
    if($data.timestamp -le $state.snapshot){throw 'duplicate_or_old_sample'}
    $gap=($dt -gt 100 -or ($state.snapshot -gt 0 -and $data.timestamp-$state.snapshot -gt 110))
    if($dt -lt 0 -or $dt -gt 360 -or ($state.snapshot -gt 0 -and $data.timestamp-$state.snapshot -gt 360)){Clear-PrinterVotes $state;$state.last_majority=0}
    if($gap){$state.last_majority=0}
    $state.snapshot=$data.timestamp;$state.last_paired=$now;$state.overlay_count=0;$state.overlay_start=0
    if(@($data.printers | Where-Object fresh -eq $true).Count -ge 12){$state.last_majority=$now}
    foreach($p in $data.printers){
        $s=$state.printers[[int]$p.n-1]
        if(!$s.PSObject.Properties['last_proof']){$s|Add-Member -NotePropertyName last_proof -NotePropertyValue 0}
        if($p.fresh){$s.good=$now}
        $known=($s.good -gt 0 -and $now -ge $s.good -and $now-$s.good -le 86400)
        $proof=[long]$p.last_good_utc
        $recentProof=($proof -gt 0 -and $proof -le $data.timestamp -and $proof -le $now -and $now-$proof -le 21600)
        if($gap -and (!$recentProof -or $p.tcp_open -or $s.last_proof -ne $proof)){$s.since=0;$s.votes=0}
        # A changed last frame is an intervening device recovery even when both
        # samples classify the printer as silent.
        if($s.last_proof -gt 0 -and $proof -ne $s.last_proof){$s.since=0;$s.votes=0}
        $s.last_proof=if($recentProof){$proof}else{0}
        if(!$p.silent -or !($known -or $recentProof)){$s.since=0;$s.votes=0;continue}
        if(!$s.since){$s.since=$now}
        $s.votes++
    }
    $state.tick=$now
}
function Mature-Machines($state,[long]$now) {
    @($state.printers | Where-Object { $_.votes -ge 3 -and $_.since -gt 0 -and $now-$_.since -ge 180 } | ForEach-Object { [int]$_.n })
}
function May-Repair($state,[string]$kind,[int]$n,[long]$now) {
    $recent=@($state.history | Where-Object { $now-$_.at -lt 86400 })
    foreach($prior in $recent){
        if($prior.at -gt $now){return $false}
        if($now-$prior.at -ge 180){continue}
        if($kind -eq 'printer' -and $prior.kind -eq 'printer' -and $prior.n -ne $n -and
           $prior.outcome -eq 'telemetry_recovered' -and $now-$prior.at -ge 60){continue}
        return $false
    }
    $all=@($recent|Where-Object kind -eq 'gateway')
    if(@($all|Where-Object { $now-$_.at -lt 3600 }).Count){return $false}
    if($kind -eq 'gateway'){return $all.Count -lt 2}
    $mine=@($recent|Where-Object {$_.kind -eq 'printer' -and $_.n -eq $n})
    if($mine.Count -ge 2 -or @($mine|Where-Object {$now-$_.at -lt 3600}).Count){return $false}
    $attempts=@($recent|Where-Object kind -eq 'printer')
    if($attempts.Count -lt 8){return $true}
    # An additional first repair needs a different machine's verified return.
    # Never refill the budget from retries or a released socket alone.
    $recovered=@($attempts|Where-Object outcome -eq 'telemetry_recovered'|Select-Object -ExpandProperty n -Unique)
    return (!$mine.Count -and $attempts.Count -lt $state.printers.Count -and $attempts.Count -lt (8+$recovered.Count))
}
function Reserve-Repair($state,$kind,$n,$reason) {
    $now=Epoch
    if(!(May-Repair $state $kind $n $now)){throw 'cooldown_or_daily_limit'}
    $state.history=@($state.history|Where-Object {$now-$_.at -lt 86400})+@([pscustomobject]@{at=$now;kind=$kind;n=$n;reason=$reason;outcome='attempted'})
    Write-AtomicJson $stateFile $state
}
function Confirm-NewHealth($config,$previous) {
    $deadline=(Epoch)+35
    for($i=0;$i -lt 6;$i++){
        try{
            $v=Read-Health $config
            if($v.timestamp -gt $previous.timestamp){return $v}
        }catch{if($_.Exception.GetBaseException().Message -ne 'status_transport_unreachable'){throw}}
        if((Epoch) -ge $deadline){break}
        Start-Sleep -Seconds 4
    }
    throw 'independent_confirmation_missing'
}
function Reset-Vpn($config,$state,$vpn,$reason) {
    $identity=Read-SiteVpn $config
    if(($identity.routes -join '|') -cne ($vpn.routes -join '|') -or $identity.other_online -ne 0){throw 'vpn_topology_changed'}
    Reserve-Repair $state 'gateway' 0 $reason
    try { Restart-Service -Name Tailscale -ErrorAction Stop }
    catch { if((Get-Service Tailscale).Status -ne 'Running'){Start-Service Tailscale -ErrorAction Stop}else{throw} }
    (Get-Service Tailscale).WaitForStatus('Running',[TimeSpan]::FromSeconds(25))
    $state.history[-1].outcome='service_running_awaiting_telemetry'
    Clear-PrinterVotes $state;$state.overlay_count=0;$state.overlay_start=0
    Write-AtomicJson $stateFile $state
}
function Release-Orphan($binding,$device,$owner) {
    [RRTcpSession]::Release($binding.ip,$owner.port,$device.ip,8883,$owner.pid)
}
function Inspect-Stalls($cfg,$state,$data,$vpn,$binding,$note) {
    $now=Epoch;$mature=@(Mature-Machines $state $now)
    $eligible=@(foreach($n in (@(17,18) + @(1..16))){if($n -in $mature){$n}})
    if(!$eligible.Count -or $vpn.other_online -ne 0){return}
    $bulk=($eligible.Count -ge 12 -and $state.last_majority -gt 0 -and $now-$state.last_majority -lt 43200 -and (May-Repair $state 'gateway' 0 $now))
    $service=Read-ServiceIdentity;$sockets=@(Read-PrinterSockets);$matches=@()
    foreach($n in $eligible){
        if(!$bulk -and ($data.printers[$n-1].tcp_open -or !(May-Repair $state 'printer' $n $now))){continue}
        $device=$cfg.devices[$n-1];$since=$state.printers[$n-1].since
        $owners=@(Read-Forwarders $device $binding $service $sockets $since | Sort-Object port)
        if(!$owners.Count -or !(Test-StalledEndpoint $device $binding)){continue}
        $matches+=@([pscustomobject]@{n=$n;owner=$owners[0]})
        if((!$bulk -and $matches.Count -eq 1) -or $matches.Count -ge 3){break}
    }
    if(!$matches.Count){return}
    $confirmation=Confirm-NewHealth $cfg $data
    $b=Get-Binding;$v=Read-SiteVpn $cfg
    if($b.ip -ne $binding.ip -or $b.index -ne $binding.index -or $v.other_online -ne 0 -or !(Test-PhysicalCloud $cfg $b)){return}
    if($bulk -and $matches.Count -ge 3 -and @($eligible | Where-Object {$confirmation.printers[$_-1].silent}).Count -ge 12){
        if(@($matches | Where-Object {!$confirmation.printers[$_.n-1].silent -or !(Test-StalledEndpoint $cfg.devices[$_.n-1] $b)}).Count){return}
        Reset-Vpn $cfg $state $vpn 'confirmed_fleet_forwarding_stall';$note.result='restarted_gateway';return
    }
    $m=$matches[0];$n=[int]$m.n;$p=$confirmation.printers[$n-1];$device=$cfg.devices[$n-1]
    if(!$p.silent -or $p.tcp_open -or !(May-Repair $state 'printer' $n (Epoch)) -or !(Test-StalledEndpoint $device $b)){return}
    if([long]$p.last_good_utc -ne [long]$data.printers[$n-1].last_good_utc){return}
    $again=@(Read-Forwarders $device $b (Read-ServiceIdentity) @(Read-PrinterSockets) $state.printers[$n-1].since | Where-Object identity -ceq $m.owner.identity)
    if($again.Count -ne 1){return}
    Reserve-Repair $state 'printer' $n 'confirmed_orphan_forwarder'
    $code=Release-Orphan $b $device $again[0]
    $state.history[-1].outcome=if($code -eq 0){'released_awaiting_telemetry'}else{'tuple_not_released_'+$code}
    $state.printers[$n-1].since=0;$state.printers[$n-1].votes=0;$note.result=$state.history[-1].outcome;$note.machine=$n
    Write-AtomicJson $stateFile $state
}
function Track-OverlayLoss($cfg,$state,$vpn,$binding,$note,[long]$now) {
    $age=$now-$state.last_paired
    if(!$state.last_paired -or $age -lt 0 -or $age -gt 3600 -or $vpn.other_online -ne 0){$state.overlay_count=0;$state.overlay_start=0;return}
    if(!(Test-PhysicalCloud $cfg $binding) -or (Test-TunnelEcho $cfg) -ne 'timeout'){$state.overlay_count=0;$state.overlay_start=0;return}
    if(!$state.overlay_start){$state.overlay_start=$now};$state.overlay_count++
    if($state.overlay_count -ge 3 -and $now-$state.overlay_start -ge 180 -and (May-Repair $state 'gateway' 0 $now)){
        # Recheck both paths immediately; a recovered tunnel cancels the action.
        if((Test-TunnelEcho $cfg) -eq 'timeout' -and (Test-PhysicalCloud $cfg $binding)){
            Reset-Vpn $cfg $state $vpn 'confirmed_overlay_loss';$note.result='restarted_gateway'
        }
    }
}
function Track-StoppedService($cfg,$state,$binding,$note,$svc,[long]$now) {
    $bin=[IO.Path]::GetFullPath((Join-Path $env:ProgramFiles 'Tailscale/tailscaled.exe'))
    if($svc.StartMode -ne 'Auto' -or $svc.PathName -notmatch '^\s*"?([^"]+?\\tailscaled\.exe)"?(?:\s|$)' -or [IO.Path]::GetFullPath($matches[1]) -ine $bin){throw 'automatic_gateway_service_unverified'}
    if(!$state.last_paired -or $now -lt $state.last_paired -or $now-$state.last_paired -gt 86400){throw 'gateway_pairing_too_old'}
    if($now-$state.tick -gt 100 -or $now -lt $state.tick){$state.stopped_since=0;$state.stopped_count=0}
    if(!(Test-PhysicalCloud $cfg $binding)){$state.stopped_since=0;$state.stopped_count=0;return}
    if(!$state.stopped_since){$state.stopped_since=$now};$state.stopped_count++;$note.result='service_stopped'
    if($state.stopped_count -ge 3 -and $now-$state.stopped_since -ge 180 -and (May-Repair $state 'gateway' 0 $now) -and (Get-Service Tailscale).Status -eq 'Stopped'){
        Reserve-Repair $state 'gateway' 0 'registered_automatic_service_stopped'
        Start-Service Tailscale -ErrorAction Stop;(Get-Service Tailscale).WaitForStatus('Running',[TimeSpan]::FromSeconds(25))
        $state.stopped_since=0;$state.stopped_count=0;$state.history[-1].outcome='service_running_awaiting_telemetry';$note.result='started_gateway_service'
    }
}
if($FunctionsOnly){return}
$root=Split-Path -Parent $PSScriptRoot
$stateFile=Join-Path $root 'state.json';$lastFile=Join-Path $root 'last-check.json'
$cfg=Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'site.json') | ConvertFrom-Json
$script:vpnExe=Join-Path $env:ProgramFiles 'Tailscale/tailscale.exe'
$lock=$null;$state=$null
$note=[ordered]@{at=Epoch;payload=(Split-Path -Leaf $PSScriptRoot);system=[Security.Principal.WindowsIdentity]::GetCurrent().IsSystem;observe_only=[bool]$ObserveOnly;result='observing';fresh=$null;silent=@();issue=$null}
try {
    if($env:COMPUTERNAME -ine $cfg.hostname){throw 'wrong_gateway_computer'}
    try { $lock=[IO.File]::Open((Join-Path $root 'guard.lock'),'OpenOrCreate','ReadWrite','None') }
    catch [IO.IOException] { return }
    $state=if(Test-Path -LiteralPath $stateFile){Get-Content -Raw -LiteralPath $stateFile|ConvertFrom-Json}else{New-GuardState}
    if($state.version -ne 1 -or (@($state.printers.n) -join ',') -ne (1..18 -join ',')){throw 'invalid_guard_state'}
    $lastAttempt=@($state.history|Select-Object -Last 1)
    $script:guardReceipt=if($lastAttempt.Count){'4|{0}|{1}|{2}' -f $lastAttempt[0].at,$lastAttempt[0].n,$lastAttempt[0].outcome}else{'4|0|0|none'}
    foreach($native in @('RRFleetStatus','RRLinkAddress','RRWiredProbe','RRTcpSession')){Add-Type -Path (Join-Path $PSScriptRoot ($native+'.cs'))}
    $binding=Get-Binding;$now=Epoch
    $svc=Get-CimInstance -ClassName Win32_Service -Filter "Name='Tailscale'" -ErrorAction Stop
    if(!$ObserveOnly -and $svc.State -eq 'Stopped'){
        Clear-PrinterVotes $state;$state.overlay_count=0;$state.overlay_start=0
        Track-StoppedService $cfg $state $binding $note $svc $now;$state.tick=$now;Write-AtomicJson $stateFile $state;return
    }
    $state.stopped_since=0;$state.stopped_count=0;$vpn=Read-SiteVpn $cfg
    try { $data=Read-Health $cfg } catch {
        $reason=$_.Exception.GetBaseException().Message
        Hold-AfterReadFailure $state $reason $now
        if($now-$state.tick -gt 100 -or $now-$state.tick -lt 0){$state.overlay_count=0;$state.overlay_start=0}
        if(!$ObserveOnly -and $reason -eq 'status_transport_unreachable'){Track-OverlayLoss $cfg $state $vpn $binding $note $now}
        else{$state.overlay_count=0;$state.overlay_start=0}
        $state.tick=$now;Write-AtomicJson $stateFile $state;throw
    }
    $note.fresh=@($data.printers|Where-Object fresh -eq $true).Count
    $note.silent=@($data.printers|Where-Object silent -eq $true|ForEach-Object n)
    $note.cloud_sample=$data.timestamp
    if($data.timestamp -eq $state.snapshot){$note.result='already_sampled';return}
    Update-Evidence $state $data $now;$note.result='sampled'
    foreach($h in @($state.history | Where-Object {$_.outcome -in @('service_running_awaiting_telemetry','released_awaiting_telemetry')})) {
        if(($h.kind -eq 'gateway' -and $note.fresh -eq 18) -or ($h.kind -eq 'printer' -and $data.printers[$h.n-1].fresh)){$h.outcome='telemetry_recovered'}
    }
    Write-AtomicJson $stateFile $state
    if(!$ObserveOnly){Inspect-Stalls $cfg $state $data $vpn $binding $note}
} catch {if($note.result -ne 'restarted_gateway'){$note.result='hold'};$note.issue=$_.Exception.GetBaseException().Message}
finally{if($lock){try{Write-AtomicJson $lastFile $note}finally{$lock.Dispose()}}}
