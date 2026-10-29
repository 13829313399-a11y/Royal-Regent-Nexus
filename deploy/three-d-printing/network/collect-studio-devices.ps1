[CmdletBinding()]
param(
    [string]$PrinterFile,
    [string]$OutputDirectory,
    [string]$PublicKeyFile,
    [string[]]$ConfigPath,
    [int[]]$MachineNumbers = @(6,7,8,15,16),
    [switch]$DiscoverCertificates,
    [ValidateRange(500,10000)][int]$ProbeTimeoutMs = 3000,
    [int[]]$CertificatePorts = @(8883,990)
)
$ErrorActionPreference = 'Stop'
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $PrinterFile) { $PrinterFile = Join-Path $scriptDirectory 'printers.csv' }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $scriptDirectory 'collected' }
if (-not $PublicKeyFile) { $PublicKeyFile = Join-Path $scriptDirectory 'recipient-public.xml' }

# Bambu Studio persists device access codes separately from its IP mapping.
# IP decoding follows the documented FNV-1a + mt19937 format in the upstream
# BBLUtil.cpp (79df7ae309be398ed30c9f397c13c9911c2edc57). No cloud account API,
# token, application log, browser store, or other user's profile is consulted.
if (-not ('RRStudioExport' -as [type])) {
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Net;
using System.Net.Sockets;
using System.Net.Security;
using System.Security.Authentication;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text.RegularExpressions;
public static class RRStudioExport {
    public sealed class CertificateObservation {
        public string Status = "tcp_failed";
        public string Serial = "";
        public string Fingerprint = "";
    }
    public static CertificateObservation ObserveCertificate(string ip, int port, int timeoutMs) {
        var result = new CertificateObservation();
        // Discovery only: accept the presented certificate to inspect it, then
        // close without sending any application bytes, credentials or commands.
        // A matching previously observed pin is checked by the caller. Neither
        // an initial observation nor a pin establishes physical device identity.
        using (var tcp = new TcpClient(AddressFamily.InterNetwork)) {
            try {
                var connect = tcp.BeginConnect(IPAddress.Parse(ip),port,null,null);
                using (var wait = connect.AsyncWaitHandle) {
                    if (!wait.WaitOne(timeoutMs)) { result.Status="tcp_timeout"; return result; }
                    tcp.EndConnect(connect);
                }
                result.Status="tls_failed";
                using (var ssl = new SslStream(tcp.GetStream(),false,delegate { return true; })) {
                    var handshake = ssl.BeginAuthenticateAsClient(ip,null,SslProtocols.Tls12,false,null,null);
                    using (var wait = handshake.AsyncWaitHandle) {
                        if (!wait.WaitOne(timeoutMs)) { result.Status="tls_timeout"; return result; }
                        ssl.EndAuthenticateAsClient(handshake);
                    }
                    using (var cert = new X509Certificate2(ssl.RemoteCertificate)) {
                        using (var hash = SHA256.Create()) result.Fingerprint=BitConverter.ToString(hash.ComputeHash(cert.RawData)).Replace("-","").ToLowerInvariant();
                        var names=cert.SubjectName.Decode(X500DistinguishedNameFlags.UseNewLines);
                        var cn=Regex.Matches(names,@"(?m)^CN=([a-zA-Z0-9_-]{1,64})\r?$");
                        result.Status="certificate_name_unsupported";
                        if (cn.Count==1) { result.Serial=cn[0].Groups[1].Value; result.Status="certificate_observed"; }
                    }
                }
            } catch { /* Sanitized stage only; no certificate or exception text. */ }
        }
        return result;
    }
    private sealed class Mt {
        private readonly uint[] state = new uint[624];
        private int index = 624;
        public Mt(uint seed) {
            state[0] = seed;
            for (int i = 1; i < 624; i++)
                state[i] = unchecked(1812433253u * (state[i-1] ^ (state[i-1] >> 30)) + (uint)i);
        }
        public uint Next() {
            if (index == 624) {
                for (int i = 0; i < 624; i++) {
                    uint x = (state[i] & 0x80000000u) | (state[(i+1)%624] & 0x7fffffffu);
                    state[i] = state[(i+397)%624] ^ (x >> 1) ^ ((x & 1u) == 0 ? 0u : 0x9908b0dfu);
                }
                index = 0;
            }
            uint y = state[index++];
            y ^= y >> 11; y ^= (y << 7) & 0x9d2c5680u;
            y ^= (y << 15) & 0xefc60000u; y ^= y >> 18;
            return y;
        }
    }
    public static string DecodeIp(string value, string uuid) {
        if (String.IsNullOrEmpty(value) || value.Length > 64) return "";
        if (value.IndexOf('.') >= 0) return value; // Older saved plaintext IP.
        if (String.IsNullOrEmpty(uuid) || uuid.Length > 256 || value.Length % 2 != 0) return "";
        uint seed = 2166136261u;
        foreach (byte b in Encoding.UTF8.GetBytes(uuid)) seed = unchecked((seed ^ b) * 16777619u);
        var mt = new Mt(seed);
        byte[] plain = new byte[value.Length / 2];
        try {
            for (int i = 0; i < plain.Length; i++)
                plain[i] = (byte)(Convert.ToByte(value.Substring(i*2,2),16) ^ (mt.Next() & 255u));
            return Encoding.ASCII.GetString(plain);
        } catch { return ""; }
    }
    public static string[] Seal(string json, string publicXml) {
        byte[] keys = new byte[64];
        using (var rng = RandomNumberGenerator.Create()) rng.GetBytes(keys);
        try {
            byte[] aesKey = new byte[32], macKey = new byte[32];
            Buffer.BlockCopy(keys,0,aesKey,0,32); Buffer.BlockCopy(keys,32,macKey,0,32);
            using (var aes = Aes.Create())
            using (var rsa = new RSACryptoServiceProvider()) {
                rsa.PersistKeyInCsp = false;
                rsa.FromXmlString(publicXml);
                if (rsa.KeySize < 3072) throw new Exception("recipient_key_invalid");
                aes.Key = aesKey; aes.GenerateIV(); aes.Mode = CipherMode.CBC; aes.Padding = PaddingMode.PKCS7;
                byte[] plain = Encoding.UTF8.GetBytes(json);
                byte[] cipher;
                using (var encryptor = aes.CreateEncryptor()) cipher = encryptor.TransformFinalBlock(plain,0,plain.Length);
                Array.Clear(plain,0,plain.Length);
                byte[] wrapped = rsa.Encrypt(keys,true); // RSA-OAEP-SHA1 for Windows PowerShell 5.1.
                byte[] authenticated = new byte[wrapped.Length + aes.IV.Length + cipher.Length];
                Buffer.BlockCopy(wrapped,0,authenticated,0,wrapped.Length);
                Buffer.BlockCopy(aes.IV,0,authenticated,wrapped.Length,aes.IV.Length);
                Buffer.BlockCopy(cipher,0,authenticated,wrapped.Length+aes.IV.Length,cipher.Length);
                using (var hmac = new HMACSHA256(macKey)) {
                    byte[] tag = hmac.ComputeHash(authenticated);
                    Array.Clear(aesKey,0,aesKey.Length); Array.Clear(macKey,0,macKey.Length);
                    return new [] {Convert.ToBase64String(wrapped),Convert.ToBase64String(aes.IV),Convert.ToBase64String(cipher),Convert.ToBase64String(tag)};
                }
            }
        } finally { Array.Clear(keys,0,keys.Length); }
    }
}
'@
}
function Read-StringProperty($Object, [string]$Name) {
    if ($null -eq $Object) { return '' }
    # Device identities and passwords are case-sensitive.
    $property = @($Object.PSObject.Properties | Where-Object { $_.Name -ceq $Name }) | Select-Object -First 1
    if ($null -ne $property -and $property.Value -is [string]) { return $property.Value }
    return ''
}
function Canonical-IPv4([string]$Value) {
    if ($Value -notmatch '^\d{1,3}(\.\d{1,3}){3}$') { return '' }
    $address = $null
    if ([Net.IPAddress]::TryParse($Value,[ref]$address) -and $address.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork -and $address.ToString() -eq $Value) { return $Value }
    return ''
}
function Parse-StudioConfig([string]$Text) {
    $format = 'json'
    $checksum = 'not_present'
    # Windows AppConfig::save appends this line after the JSON object. It is
    # not JSON, and must not be passed to Windows PowerShell ConvertFrom-Json.
    # Strip only the recognized final line, never arbitrary trailing content.
    $trailer = [regex]::Match($Text,'\r?\n# MD5 checksum [a-fA-F0-9]{32}(?:\r?\n)?[ \t]*\z')
    if ($trailer.Success) {
        $Text = $Text.Substring(0,$trailer.Index)
        $format = 'json_with_windows_checksum'
        $checksum = 'present_not_verified'
    }
    $document = ConvertFrom-Json -InputObject $Text -ErrorAction Stop
    if ($document -isnot [pscustomobject]) { throw 'unsupported_config_root' }
    return @{document=$document;format=$format;checksum=$checksum}
}
try {
    $allPrinters = @(Import-Csv -LiteralPath $PrinterFile)
    $targets = @($allPrinters | Where-Object { [int]$_.machine_no -in $MachineNumbers })
    if ($MachineNumbers.Count -lt 1 -or $MachineNumbers.Count -gt 16 -or $targets.Count -ne $MachineNumbers.Count -or
        @($targets.machine_no | Select-Object -Unique).Count -ne $targets.Count -or
        @($targets.ip | Select-Object -Unique).Count -ne $targets.Count -or
        @($targets.credential_ref | Select-Object -Unique).Count -ne $targets.Count) { throw 'invalid_targets' }
    foreach ($row in $targets) {
        if ([int]$row.machine_no -lt 1 -or [int]$row.machine_no -gt 16 -or -not (Canonical-IPv4 $row.ip) -or $row.credential_ref -notmatch '^printer-[0-9]{2}$') { throw 'invalid_target' }
        $pin = Read-StringProperty $row 'observed_cert_sha256'
        if ($pin -and $pin -notmatch '^[a-fA-F0-9]{64}$') { throw 'invalid_observed_pin' }
    }
    if ($CertificatePorts.Count -lt 1 -or $CertificatePorts.Count -gt 2 -or @($CertificatePorts | Where-Object {$_ -lt 1 -or $_ -gt 65535}).Count) { throw 'invalid_certificate_ports' }
    $publicXml = [IO.File]::ReadAllText($PublicKeyFile)
    if ($publicXml.Length -gt 8192 -or $publicXml -match '<(D|P|Q)>') { throw 'public_key_required' }
    if (-not $ConfigPath) {
        $appDataDirectory = [Environment]::GetFolderPath('ApplicationData')
        $ConfigPath = @((Join-Path $appDataDirectory 'BambuStudio\BambuStudio.conf'), (Join-Path $appDataDirectory 'BambuStudioBeta\BambuStudio.conf'))
    }
    if ($ConfigPath.Count -gt 4) { throw 'too_many_config_paths' }
    $configs = @(); $candidates = @(); $profiles = @(); $configIndex = 0
    foreach ($path in @($ConfigPath | Select-Object -Unique)) {
        $configIndex++
        $label = 'config-' + $configIndex
        $info = [ordered]@{source=$label;status='not_found';read_stage='locate';format='unknown';checksum='unknown';size_bytes=0;mapping_entries=0;matched_target_entries=0;access_code_entries=0;user_access_code_entries=0;issue_code=''}
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { $configs += $info; continue }
        try {
            $info.read_stage = 'metadata'
            $item = Get-Item -LiteralPath $path
            $info.size_bytes = $item.Length
            if ($item.Length -gt 4194304 -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'unsupported_config_file' }
            $info.read_stage = 'read_file'
            $raw = [IO.File]::ReadAllText($item.FullName)
            $info.read_stage = 'parse_json'
            $parsed = Parse-StudioConfig $raw
            $document = $parsed.document
            $info.format = $parsed.format
            $info.checksum = $parsed.checksum
            $info.read_stage = 'read_mapping'
            foreach ($section in @('access_code','user_access_code')) {
                if ($document.$section -is [pscustomobject]) { $info[($section + '_entries')] = @($document.$section.PSObject.Properties).Count }
            }
            $profiles += [pscustomobject]@{source=$label;access_code=$document.access_code;user_access_code=$document.user_access_code}
            $uuid = Read-StringProperty $document.app 'slicer_uuid'
            if (-not $uuid) { $uuid = Read-StringProperty $document 'slicer_uuid' }
            $mapping = $document.user_access_dev_ip
            if ($mapping -isnot [pscustomobject]) { $info.status='no_saved_ip_mapping'; continue }
            $info.status = 'read_saved_ip_mapping'
            $info.mapping_entries = @($mapping.PSObject.Properties).Count
            foreach ($property in $mapping.PSObject.Properties) {
                if ($property.Name -notmatch '^[a-zA-Z0-9_-]{1,64}$' -or $property.Value -isnot [string]) { continue }
                $ip = Canonical-IPv4 ([RRStudioExport]::DecodeIp($property.Value,$uuid))
                if (-not $ip -or $ip -notin $targets.ip) { continue }
                $info.matched_target_entries++
                $serial = $property.Name
                $code = Read-StringProperty $document.user_access_code $serial
                $codeSource = 'user_access_code'
                if (-not $code) { $code = Read-StringProperty $document.access_code $serial; $codeSource = 'access_code' }
                $candidates += [pscustomobject]@{ip=$ip;serial=$serial;access_code=$code;source=$label;code_source=$codeSource;identity_source='bambu_studio_saved_ip_mapping'}
            }
        } catch {
            $info.status = 'unreadable_or_unsupported'
            # Never serialize the exception text or ErrorRecord: JSON parse
            # errors may include the original configuration and account data.
            $info.issue_code = switch ($info.read_stage) {
                'metadata' { 'file_metadata_or_size_unsupported' }
                'read_file' { 'file_read_failed' }
                'parse_json' { 'json_parse_or_root_unsupported' }
                default { 'saved_mapping_read_failed' }
            }
        }
        finally { $configs += $info; $document=$null; $parsed=$null; $raw=$null }
    }
    $discovery = @(); $blockedIps = @(); $observed = @{}
    if ($DiscoverCertificates) {
        foreach ($target in $targets) {
            $attempts = @(); $discoveryState = 'certificate_not_observed'; $pinState = 'not_checked'
            $expectedPin = Read-StringProperty $target 'observed_cert_sha256'
            foreach ($port in $CertificatePorts) {
                $probe = [RRStudioExport]::ObserveCertificate($target.ip,$port,$ProbeTimeoutMs)
                $attempts += [ordered]@{port=$port;status=$probe.Status;observed_cert_sha256=$probe.Fingerprint}
                if ($probe.Status -ne 'certificate_observed') { continue }
                if ($expectedPin -and $probe.Fingerprint -cne $expectedPin.ToLowerInvariant()) {
                    $discoveryState='certificate_pin_mismatch'; $pinState='mismatch'; $blockedIps += $target.ip
                    break
                }
                $pinState = if ($expectedPin) { 'matches_previous_observation' } else { 'first_observation_not_verified' }
                $observed[$target.ip] = [pscustomobject]@{serial=$probe.Serial;fingerprint=$probe.Fingerprint;port=$port;pin_status=$pinState}
                $discoveryState='certificate_observed_no_saved_code'
                $foundCode = $false
                foreach ($profile in $profiles) {
                    $code=Read-StringProperty $profile.user_access_code $probe.Serial
                    $codeSource='user_access_code'
                    if (-not $code) { $code=Read-StringProperty $profile.access_code $probe.Serial; $codeSource='access_code' }
                    if (-not $code) { continue }
                    $foundCode=$true
                    $candidates += [pscustomobject]@{ip=$target.ip;serial=$probe.Serial;access_code=$code;source=$profile.source;code_source=$codeSource;identity_source='tls_certificate_name_and_saved_code'}
                    $discoveryState='certificate_matched_saved_code'
                }
                # Keep a missing-code identity in conflict checks, without letting
                # an unrelated config lacking this serial invalidate a valid code.
                if (-not $foundCode) {
                    $candidates += [pscustomobject]@{ip=$target.ip;serial=$probe.Serial;access_code='';identity_source='tls_certificate_name_and_saved_code'}
                }
                break
            }
            $discovery += [ordered]@{machine_no=[int]$target.machine_no;ip=$target.ip;status=$discoveryState;pin_status=$pinState;attempts=$attempts}
        }
    }
    $records = @(); $publicRows = @()
    foreach ($target in $targets) {
        $matches = @($candidates | Where-Object { $_.ip -eq $target.ip })
        $identities = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([StringComparer]::Ordinal)
        foreach ($match in $matches) { $identities[$match.serial + [char]0 + $match.access_code] = $match }
        $unique = @($identities.Values)
        $observation = $observed[$target.ip]
        $state = 'not_found_in_saved_ip_mapping'
        if (@($configs | Where-Object {$_.status -eq 'read_saved_ip_mapping'}).Count -eq 0) {
            $state = if (@($configs | Where-Object {$_.status -eq 'no_saved_ip_mapping'}).Count) { 'saved_ip_mapping_unavailable' } else { 'configuration_unavailable' }
        }
        if ($target.ip -in $blockedIps) { $state='certificate_pin_mismatch' }
        elseif ($unique.Count -gt 1 -or ($observation -and @($matches | Where-Object {$_.serial -cne $observation.serial}).Count)) { $state = 'ambiguous_saved_identity_or_code' }
        elseif ($unique.Count -eq 1) {
            $candidate = $unique[0]
            $serialIps = @($candidates | Where-Object { $_.serial -ceq $candidate.serial } | Select-Object -ExpandProperty ip -Unique)
            if ($serialIps.Count -ne 1) { $state='ambiguous_saved_identity_or_code' }
            elseif ($candidate.access_code.Length -lt 1 -or $candidate.access_code.Length -gt 128 -or $candidate.access_code -match '[\x00-\x1f]') { $state='access_code_missing_or_invalid' }
            else {
                $state = 'saved_credentials_collected_not_authenticated'
                $record = [ordered]@{machine_no=[int]$target.machine_no;ip=$target.ip;credential_ref=$target.credential_ref;serial=$candidate.serial;access_code=$candidate.access_code;identity_source=$candidate.identity_source;mqtt_authenticated=$false;physical_identity_verified=$false}
                if ($observation) { $record.observed_cert_sha256=$observation.fingerprint; $record.certificate_port=$observation.port; $record.pin_status=$observation.pin_status }
                $records += $record
            }
        }
        $publicRows += [ordered]@{machine_no=[int]$target.machine_no;ip=$target.ip;credential_ref=$target.credential_ref;status=$state}
    }
    # Inspect current sockets separately from the bounded certificate probes.
    $sockets = @(); $socketStatus = 'unavailable'
    try {
        if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
            $sockets = @(Get-NetTCPConnection -ErrorAction Stop | Where-Object { $_.RemoteAddress -in $allPrinters.ip } | ForEach-Object {
                $process = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
                [ordered]@{ip=$_.RemoteAddress;remote_port=[int]$_.RemotePort;state=[string]$_.State;process_name=if($process){$process.ProcessName}else{'unknown'}}
            })
            $socketStatus = 'inspected'
        }
    } catch { $socketStatus='unavailable' }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $runDirectory = Join-Path $OutputDirectory ('studio-' + $stamp + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
    if (Test-Path -LiteralPath $runDirectory) { throw 'output_exists' }
    New-Item -ItemType Directory -Path $runDirectory | Out-Null
    $utf8 = [Text.UTF8Encoding]::new($false)
    $exportName = ''
    if ($records.Count -gt 0) {
        $payload = [ordered]@{version=1;factory_id='huakang-a';collected_at=(Get-Date).ToUniversalTime().ToString('o');printers=$records}
        $sealed = [RRStudioExport]::Seal(($payload | ConvertTo-Json -Depth 8 -Compress),$publicXml)
        $envelope = [ordered]@{version=1;algorithm='RSA-OAEP-SHA1+AES-256-CBC+HMAC-SHA256';wrapped_key=$sealed[0];iv=$sealed[1];ciphertext=$sealed[2];tag=$sealed[3]}
        $exportName = 'device-secrets.encrypted.json'
        [IO.File]::WriteAllText((Join-Path $runDirectory $exportName),($envelope | ConvertTo-Json),$utf8)
    }
    $report = [ordered]@{collector_version=3;purpose='targeted_saved_studio_config_no_printer_commands';collected_at=(Get-Date).ToUniversalTime().ToString('o');targets=$publicRows;config_sources=$configs;certificate_discovery_enabled=[bool]$DiscoverCertificates;certificate_discovery=$discovery;socket_inspection=$socketStatus;existing_printer_connections=$sockets;encrypted_export=$exportName;plaintext_credentials_written=$false;mqtt_authenticated=$false;files_uploaded=$false}
    [IO.File]::WriteAllText((Join-Path $runDirectory 'collection-report.json'),($report | ConvertTo-Json -Depth 8),$utf8)
    $publicRows | ForEach-Object {[pscustomobject]$_} | Format-Table machine_no,ip,status -AutoSize
    Write-Output "Collected $($records.Count) of $($targets.Count) saved device credentials. No authentication attempted."
    Write-Output "Results: $runDirectory"
    Write-Output 'Share collection-report.json and, if present, device-secrets.encrypted.json. Do not share the original Studio config.'
} catch {
    Write-Error 'Collection could not complete. Check the printer CSV, recipient public key, configuration path and output folder. No original configuration was changed.'
    exit 1
}
