$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'guard.ps1') -FunctionsOnly
function Assert($value,$why){if(!$value){throw $why}}
function Epoch { $script:at }
function Cloud($time,$silent) {
    [pscustomobject]@{timestamp=$time;printers=@(foreach($i in 1..18){[pscustomobject]@{n=$i;fresh=($i -notin $silent);silent=($i -in $silent);tcp_open=($i -notin $silent)}})}
}
$cfg=[pscustomobject]@{devices=@(1..18|ForEach-Object{[pscustomobject]@{no=$_;ip="192.168.1.$_"}})}
function Scenario($silent) {
    $state=New-GuardState;$script:at=100000;$d=Cloud $script:at @();Update-Evidence $state $d $script:at
    foreach($age in @(60,120,180,240)){$script:at=100000+$age;$d=Cloud $script:at $silent;Update-Evidence $state $d $script:at}
    return $state
}
$state=Scenario @();Assert (@(Mature-Machines $state $at).Count -eq 0) 'healthy telemetry must win even if auxiliary TLS tests fail'
$state=Scenario @(18);Assert ((@(Mature-Machines $state $at) -join ',') -eq '18') 'isolated stale printer'
$d=Cloud ($at+60) @();Update-Evidence $state $d ($at+60);Assert (@(Mature-Machines $state ($at+60)).Count -eq 0) 'new device frame must cancel repair'
$state=Scenario @(18);$d=Cloud ($at+190) @(18);Update-Evidence $state $d ($at+190);Assert (@(Mature-Machines $state ($at+190)).Count -eq 0) 'missed intervals cannot count'
$state=New-GuardState;$d=Cloud 99999 (1..18);Update-Evidence $state $d 99999;Assert (!$state.printers[17].votes) 'offline at installation is not a verified failure'
$state=New-GuardState
foreach($time in @(100000,100060,100120,100180)){
    $d=Cloud $time (1..18)
    foreach($pair in @(@(1,99000),@(2,75000),@(3,105000))){
        $d.printers[$pair[0]-1]|Add-Member -NotePropertyName last_good_utc -NotePropertyValue $pair[1]
    }
    Update-Evidence $state $d $time
    if($time -lt 100180){Assert (@(Mature-Machines $state $time).Count -eq 0) 'cloud history cannot waive the full observation interval'}
}
Assert ((@(Mature-Machines $state 100180) -join ',') -ceq '1') 'only a recent confirmed device frame can bootstrap an individual'
Assert (!$state.last_majority -and !$state.printers[0].good) 'history cannot impersonate current telemetry'
$d=Cloud 100240 (1..18);Update-Evidence $state $d 100240
Assert (@(Mature-Machines $state 100240).Count -eq 0) 'historical evidence withdrawn on lease change'
# Replay the field sequence: successful reads separated by failures on the VPN.
function SilentWithProof($when,$proof) {
    $cloud=Cloud $when (1..18)
    $cloud.printers[0]|Add-Member -NotePropertyName last_good_utc -NotePropertyValue $proof
    return $cloud
}
$state=New-GuardState
foreach($when in @(100000,100060)){Update-Evidence $state (SilentWithProof $when 99000) $when}
Hold-AfterReadFailure $state 'status_transport_unreachable' 100120
Assert ($state.printers[0].votes -eq 2 -and !@(Mature-Machines $state 100200).Count) 'missing reads cannot manufacture votes'
Update-Evidence $state (SilentWithProof 100300 99000) 100300
Assert ((@(Mature-Machines $state 100300) -join ',') -ceq '1' -and !$state.last_majority) 'same independently proven frame may bridge a short gap for its printer'
Hold-AfterReadFailure $state 'status_transport_unreachable' 100360
Update-Evidence $state (SilentWithProof 100550 100305) 100550
Assert ($state.printers[0].votes -eq 1 -and $state.printers[0].since -eq 100550) 'intervening recovered frame restarts observations'
Hold-AfterReadFailure $state 'status_certificate_rejected' 100610
Assert (!$state.printers[0].votes) 'certificate or integrity failure clears evidence'
Update-Evidence $state (SilentWithProof 101000 100305) 101000
Assert ($state.printers[0].votes -eq 1) 'extended gap cannot be bridged'
$binding=[pscustomobject]@{ip='192.168.1.199';index=4};$vpn=[pscustomobject]@{other_online=0;routes=@('demo')}
function Read-ServiceIdentity { 'service' };function Read-PrinterSockets{ 'socket' };function Get-Binding{$binding};function Read-SiteVpn($c){$vpn}
function Read-Forwarders($device,$b,$service,$sockets,$since){[pscustomobject]@{port=45001;pid=33;identity='tuple-'+$device.no}}
function Test-StalledEndpoint($device,$b){return ($device.no -in $script:stalled)}
function Test-PhysicalCloud($c,$b){return $script:physical}
function Confirm-NewHealth($c,$data){return $script:next}
function Write-AtomicJson($p,$s){}
function Reset-Vpn($c,$s,$v,$reason){$script:actions+=@('gateway')}
function Release-Orphan($b,$device,$owner){$script:actions+=@('printer-'+$device.no);return 0}
function Test-TunnelEcho($c){return $script:echo}
$script:physical=$true;$stateFile='mock';$stalled=1..18
function Exercise($silent,$newSilent,$busy,$expect){
    $script:actions=@();$state=Scenario $silent;$d=Cloud $at $silent;$script:next=Cloud ($at+20) $newSilent
    foreach($i in $busy){$d.printers[$i-1].tcp_open=$true;$script:next.printers[$i-1].tcp_open=$true}
    $note=@{};Inspect-Stalls $cfg $state $d $vpn $binding $note
    Assert (($script:actions -join ',') -ceq $expect) ('unexpected repair: '+($script:actions -join ','))
}
Exercise @() @() @() ''
Exercise @(18) @(18) @(18) ''
Exercise @(18) @() @() ''
Exercise @(18) @(18) @() 'printer-18'
Exercise @(1,8,17,18) @(1,8,17,18) @() 'printer-17'
Exercise @(1,8,18) @(1,8,18) @() 'printer-18'
Exercise (1..16) (1..16) @() 'gateway'
$script:physical=$false;Exercise (1..16) (1..16) @() ''; $script:physical=$true
$vpn.other_online=1;Exercise @(18) @(18) @() ''; $vpn.other_online=0
$stalled=@();Exercise (1..16) (1..16) @() ''; $stalled=1..18
$state=Scenario @(18);$state.history=@([pscustomobject]@{at=$at-900;kind='gateway';n=0});Assert (!(May-Repair $state 'gateway' 0 $at)) 'cooldown across process restarts'
$state.history=@([pscustomobject]@{at=$at-6000;kind='gateway';n=0},[pscustomobject]@{at=$at-12000;kind='gateway';n=0});Assert (!(May-Repair $state 'gateway' 0 $at)) 'daily restart limit'
$state.history=@([pscustomobject]@{at=$at-65;kind='printer';n=1;outcome='released_awaiting_telemetry'})
Assert (!(May-Repair $state 'printer' 4 $at)) 'no accelerated action while the previous result is unknown'
$state.history[0].outcome='telemetry_recovered'
Assert ((May-Repair $state 'printer' 4 $at) -and !(May-Repair $state 'printer' 1 $at) -and !(May-Repair $state 'gateway' 0 $at)) 'a separately proven recovered printer can release the next isolated repair after one minute'
$state.history=@(1..8|ForEach-Object{[pscustomobject]@{at=$at-8000;kind='printer';n=$_;outcome='released_awaiting_telemetry'}})
Assert (!(May-Repair $state 'printer' 17 $at)) 'eight unconfirmed attempts must still block additional repairs'
$state.history[0].outcome='telemetry_recovered'
Assert ((May-Repair $state 'printer' 17 $at) -and !(May-Repair $state 'printer' 1 $at)) 'only a first repair can use an independently confirmed return'
$state.history+=@([pscustomobject]@{at=$at-500;kind='printer';n=17;outcome='released_awaiting_telemetry'})
Assert (!(May-Repair $state 'printer' 18 $at)) 'each confirmed device can credit only one additional attempt'
$state.history[1].outcome='telemetry_recovered'
Assert ((May-Repair $state 'printer' 18 $at)) 'a second independently recovered machine unlocks the next first repair'
$state.history=@(1..18|ForEach-Object{[pscustomobject]@{at=$at-8000;kind='printer';n=$_;outcome='telemetry_recovered'}})
Assert (!(May-Repair $state 'printer' 17 $at)) 'total attempts remain bounded to fleet size per rolling day'
$state=Scenario @();$script:actions=@();$script:echo='pong';foreach($i in 1..4){$script:at+=60;Track-OverlayLoss $cfg $state $vpn $binding @{} $at};Assert (!$actions.Count) 'status service unavailable with a healthy tunnel'
$script:echo='timeout';foreach($i in 1..4){$script:at+=60;Track-OverlayLoss $cfg $state $vpn $binding @{} $at};Assert (($actions -join ',') -eq 'gateway') 'persistent isolated overlay failure'
$script:at=100000
foreach($dev in $cfg.devices){$dev|Add-Member -NotePropertyName mac -NotePropertyValue ('mac-'+$dev.no)}
function Read-Health($c){$d=Cloud $at @(2,3,4,5);$d.printers[2].tcp_open=$true;return $d}
function Get-NetTCPConnection {throw 'unavailable in simulation'}
function Read-PrinterLink($dev,$b){
    if($dev.no -eq 4){return @{code=1;mac=$null}}
    if($dev.no -eq 5){return @{code=0;mac='other'}}
    return @{code=0;mac=$dev.mac}
}
function Read-PrinterPort($dev,$b){$script:probed+=@($dev.no);return @{interface_forced=$true;status='failed';error='timeout'}}
$script:probed=@();$diag=Get-InstallDiagnostics $cfg
Assert (($diag.devices.n -join ',') -ceq '2,3,4,5') 'read-only receipt lists only currently silent machines'
Assert (($script:probed -join ',') -ceq '2') 'fresh, active cloud socket, unresolved and mismatched MAC must skip auxiliary connection'
Assert (($diag.devices.lan_tcp -join ',') -ceq 'timeout,skipped_cloud_socket,not_tested,not_tested') 'field probe outcomes'
Assert ($null -eq $diag.devices[0].verified_gateway_sockets -and $diag.issue -eq 'gateway_socket_inventory_unavailable') 'unavailable inventory stays unknown'
Write-Output 'Gateway recovery policy tests passed.'
