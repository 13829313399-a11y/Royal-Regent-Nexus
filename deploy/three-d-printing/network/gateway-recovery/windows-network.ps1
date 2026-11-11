function Get-VpnJson([string]$Arguments) {
    $start = [Diagnostics.ProcessStartInfo]::new($script:vpnExe,$Arguments)
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $p = [Diagnostics.Process]::new()
    try {
        $p.StartInfo = $start
        if (!$p.Start()) { throw 'vpn_cli_unavailable' }
        $o = $p.StandardOutput.ReadToEndAsync(); $e = $p.StandardError.ReadToEndAsync()
        if (!$p.WaitForExit(11000)) { $p.Kill(); throw 'vpn_cli_timeout' }
        if ($p.ExitCode -ne 0) { throw 'vpn_cli_failed' }
        return ($o.Result | ConvertFrom-Json)
    } finally { $p.Dispose() }
}

function Get-Binding {
    $candidates = @(foreach ($a in @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop | Where-Object { $_.IPAddress -like '__PRINTER_LAN_PREFIX__.*' -and $_.PrefixLength -eq 24 -and $_.AddressState -eq 'Preferred' })) {
        $n = Get-NetAdapter -InterfaceIndex $a.InterfaceIndex -ErrorAction Stop
        $r = @(Get-NetRoute -InterfaceIndex $a.InterfaceIndex -AddressFamily IPv4 -DestinationPrefix '__PRINTER_LAN_PREFIX__.0/24' -ErrorAction SilentlyContinue | Where-Object NextHop -eq '0.0.0.0')
        $def = @(Get-NetRoute -InterfaceIndex $a.InterfaceIndex -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Sort-Object RouteMetric)
        if ($n.Status -eq 'Up' -and $n.HardwareInterface -and $r.Count -and $def.Count -and $def[0].NextHop -like '__PRINTER_LAN_PREFIX__.*') {
            [pscustomobject]@{ip=$a.IPAddress;index=[int]$a.InterfaceIndex;router=$def[0].NextHop;description=[string]$n.InterfaceDescription}
        }
    })
    if ($candidates.Count -ne 1) { throw 'physical_printer_network_binding_ambiguous' }
    return $candidates[0]
}

function Read-ServiceIdentity {
    $svc=Get-CimInstance -ClassName Win32_Service -Filter "Name='Tailscale'" -ErrorAction Stop
    if (!$svc -or $svc.State -ne 'Running' -or $svc.ProcessId -le 0) { throw 'gateway_service_not_running' }
    $proc=Get-CimInstance -ClassName Win32_Process -Filter ('ProcessId='+[int]$svc.ProcessId) -ErrorAction Stop
    if (!$proc -or $proc.Name -ine 'tailscaled.exe' -or !$proc.ExecutablePath -or !$proc.CreationDate) { throw 'gateway_service_identity_unavailable' }
    return $proc
}

function Read-Owner($Service,[int]$OwnerId) {
    $info=[ordered]@{pid=$OwnerId; name=$null; parent_pid=$null; service_pid=[int]$Service.ProcessId; role='process_unavailable';
        same_executable=$null; same_session=$null; subproc_argument=$null; started_at=$null}
    try {
        $p=if ($OwnerId -eq $Service.ProcessId) { $Service } else {
            Get-CimInstance -ClassName Win32_Process -Filter ('ProcessId='+$OwnerId) -ErrorAction Stop
        }
    } catch { $info.role='process_query_unavailable';return $info }
    if (!$p) { return $info }
    $info.name=[string]$p.Name
    $info.parent_pid=[int]$p.ParentProcessId
    $info.same_session=($p.SessionId -eq $Service.SessionId)
    $info.subproc_argument=([string]$p.CommandLine -match '(?:^|\s)"?/subproc"?(?=\s|$)')
    if ($p.CreationDate) { $info.started_at=([DateTime]$p.CreationDate).ToUniversalTime().ToString('o') }
    if ($p.ExecutablePath) {
        $info.same_executable=[string]::Equals([IO.Path]::GetFullPath($Service.ExecutablePath),[IO.Path]::GetFullPath($p.ExecutablePath),[StringComparison]::OrdinalIgnoreCase)
    }
    if ($OwnerId -eq $Service.ProcessId) { $info.role='service' }
    elseif ($p.Name -ine 'tailscaled.exe') { $info.role='other_program' }
    elseif ($info.parent_pid -ne $Service.ProcessId) { $info.role='not_service_child' }
    elseif (!$info.same_executable) { $info.role='different_or_unverified_executable' }
    elseif (!$info.same_session) { $info.role='different_process_session' }
    elseif (!$info.subproc_argument) { $info.role='different_or_unverified_worker_mode' }
    elseif (!$p.CreationDate -or ([DateTime]$p.CreationDate).ToUniversalTime() -lt ([DateTime]$Service.CreationDate).ToUniversalTime()) { $info.role='worker_start_unverified' }
    else { $info.role='service_worker' }
    return $info
}

function Convert-LocalIPv4([string]$Address) {
    $ip=$null
    if (![Net.IPAddress]::TryParse($Address,[ref]$ip)) { return $null }
    if ($ip.IsIPv4MappedToIPv6) { $ip=$ip.MapToIPv4() }
    if ($ip.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork) { return $ip.ToString() }
    return $null
}

function Read-SiteVpn($config) {
    if ($env:COMPUTERNAME -ine $config.hostname) { throw 'wrong_gateway_computer' }
    $s=Get-VpnJson 'status --json'
    if ($s.Self.ID -and $s.Self.ID -cne $config.site_id) { throw 'different_gateway_identity' }
    $addresses=@($s.Self.TailscaleIPs | Where-Object { $_ -match '^\d+\.' })
    if ($addresses.Count -and $config.gateway -notin $addresses) { throw 'different_gateway_address' }
    if (!$s.Self.ID -or !$addresses.Count -or $s.BackendState -ne 'Running') { throw 'gateway_identity_or_login_not_ready' }
    $peers=@($s.Peer.PSObject.Properties.Value)
    $peer=@($peers | Where-Object { $_.ID -ceq $config.cloud_id -and $config.cloud -in @($_.TailscaleIPs) })
    if ($peer.Count -ne 1) { throw 'cloud_peer_identity_unavailable' }
    $prefs=Get-VpnJson 'debug prefs'
    if(@($config.devices | Where-Object { ($_.ip+'/32') -notin @($prefs.AdvertiseRoutes) }).Count){throw 'printer_routes_changed'}
    [pscustomobject]@{other_online=@($peers | Where-Object { $_.ID -cne $config.cloud_id -and $_.Online }).Count; routes=@($prefs.AdvertiseRoutes|Sort-Object)}
}

function Read-Forwarders($device,$binding,$service,$connections,[long]$olderThan) {
    foreach($c in $connections) {
        if ((Convert-LocalIPv4 $c.RemoteAddress) -ne $device.ip -or (Convert-LocalIPv4 $c.LocalAddress) -ne $binding.ip) { continue }
        if (!$c.CreationTime -or ([DateTime]$c.CreationTime).Year -lt 2020) { continue }
        $created=([DateTimeOffset]([DateTime]$c.CreationTime)).ToUnixTimeSeconds()
        if($created -gt $olderThan){continue}
        $owner=Read-Owner $service ([int]$c.OwningProcess)
        if($owner.role -notin @('service','service_worker') -or !$owner.started_at){continue}
        [pscustomobject]@{port=[int]$c.LocalPort;pid=[int]$c.OwningProcess;identity=('{0}|{1}|{2}|{3}|{4}' -f $c.LocalPort,$c.OwningProcess,([DateTime]$c.CreationTime).ToUniversalTime().Ticks,$owner.started_at,$service.ProcessId)}
    }
}
function Read-PrinterSockets {
    @(Get-NetTCPConnection -RemotePort 8883 -State Established -ErrorAction SilentlyContinue)
}
function Read-PrinterLink($device,$binding) {
    [RRLinkAddress]::Lookup($binding.ip,$device.ip)
}
function Read-PrinterPort($device,$binding) {
    [RRWiredProbe]::Check($binding.ip,$binding.index,$device.ip,8883,1500)
}
function Test-StalledEndpoint($device,$binding) {
    $link=Read-PrinterLink $device $binding
    if($link.code -ne 0 -or !$link.mac -or $link.mac -ine $device.mac){return $false}
    $tcp=Read-PrinterPort $device $binding
    return ($tcp.interface_forced -and $tcp.error -in @('TimedOut','timeout'))
}
function Test-PhysicalCloud($config,$binding) {
    $test=[RRWiredProbe]::Check($binding.ip,$binding.index,$config.public_cloud,22,2200)
    if (!$test.interface_forced -or $test.status -ne 'ok'){return $false}
    $ping=[Net.NetworkInformation.Ping]::new()
    try {return $ping.Send($binding.router,1500).Status -eq 'Success'} catch {return $false} finally {$ping.Dispose()}
}
function Test-TunnelEcho($config) {
    # The normal exit status alone does not confirm a TSMP pong.
    $output=(& $script:vpnExe ping --tsmp --c=1 --timeout=3s $config.cloud 2>&1 | Out-String)
    if($output -match '(?im)^pong from '){return 'pong'}
    if($output -match '(?i)timed out|timeout|no reply'){return 'timeout'}
    return 'unknown'
}
