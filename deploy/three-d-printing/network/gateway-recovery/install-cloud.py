"""Install the private listener and sampler on the existing Linux observer host."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile


SOURCE = Path(__file__).resolve().parent
LIB = Path('/usr/local/lib/rr-three-d-gateway-health')
ETC = Path('/etc/rr-three-d-gateway-health')
STATUS = Path('/run/rr-three-d-gateway-health/status.json')
UNITS = Path('/etc/systemd/system')
NAME = 'rr-three-d-gateway-health'
SAMPLE = NAME + '-sample'
PORT = 18443
API = 'royal-regent-nexus-api-1'
CONNECTOR = 'rr-three-d-printer-connector-1'


def run(*args):
    return subprocess.check_output(args, text=True, timeout=45).strip()


def put(path, payload, mode):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        f.write(payload)
        os.fchmod(f.fileno(), mode)
        pending = Path(f.name)
    os.replace(pending, path)


def main():
    if os.getuid() != 0:
        raise ValueError('requires root on the cloud observer')
    network = json.loads(Path(sys.argv[1]).read_text())
    gateway = str(ipaddress.IPv4Address(network['gateway_ip']))
    status = json.loads(run('tailscale', 'status', '--json'))
    cloud = next(str(ipaddress.IPv4Address(ip)) for ip in status['TailscaleIPs'] if ':' not in ip)
    if any(ipaddress.ip_address(ip) not in ipaddress.ip_network('100.64.0.0/10') for ip in (gateway, cloud)):
        raise ValueError('expected Tailscale IPs')
    peers = [p for p in status['Peer'].values() if gateway in (p.get('TailscaleIPs') or []) and p.get('HostName','').lower() == '3d']
    if len(peers) != 1 or cloud == gateway:
        raise ValueError('site identity unavailable')
    # Validate live data before installing or changing any systemd unit.
    from sample import collect
    data = collect(API, CONNECTOR, gateway)
    if not data['collector_ok'] or not data['routes_ok']:
        raise ValueError('observer not ready')
    files = {
        SAMPLE+'.service': f'''[Unit]
Description=Read 3D device telemetry for the factory gateway
After=docker.service tailscaled.service
[Service]
Type=oneshot
RuntimeDirectory=rr-three-d-gateway-health
RuntimeDirectoryPreserve=yes
TimeoutStartSec=25
ExecStart=/usr/bin/python3 {LIB}/sample.py {STATUS} {API} {CONNECTOR} {gateway}
''',
        SAMPLE+'.timer': f'''[Unit]
Description=Refresh 3D gateway evidence
[Timer]
OnBootSec=25s
OnUnitActiveSec=20s
AccuracySec=2s
Unit={SAMPLE}.service
[Install]
WantedBy=timers.target
''',
        NAME+'.socket': f'''[Unit]
Description=3D status socket on Tailscale only
[Socket]
ListenStream={cloud}:{PORT}
BindToDevice=tailscale0
FreeBind=yes
NoDelay=yes
[Install]
WantedBy=sockets.target sys-subsystem-net-devices-tailscale0.device
''',
        NAME+'.service': f'''[Unit]
Description=Read-only health feed for the single factory gateway
Requires={NAME}.socket
After={NAME}.socket
[Service]
DynamicUser=yes
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
CapabilityBoundingSet=
RestrictAddressFamilies=AF_INET AF_UNIX
LoadCredential=server.key:{ETC}/server.key
LoadCredential=server.crt:{ETC}/server.crt
ExecStart=/usr/bin/python3 {LIB}/serve.py {gateway} {STATUS}
Restart=on-failure
RestartSec=3s
'''}
    marker = '# Managed by Nexus 3D gateway recovery\n'
    paths = {UNITS / name: (marker + value).encode() for name, value in files.items()}
    for path in paths:
        if path.exists() and not path.read_text().startswith(marker):
            raise ValueError('unit already belongs to another service')
    if not (UNITS / (NAME+'.socket')).exists() and run('ss','-Hln','sport','=',f':{PORT}'):
        raise ValueError('port already in use')
    LIB.mkdir(mode=0o755, exist_ok=True)
    ETC.mkdir(mode=0o700, exist_ok=True)
    key, cert = ETC/'server.key', ETC/'server.crt'
    if key.exists() != cert.exists():
        raise ValueError('incomplete existing TLS identity')
    if not key.exists():
        with tempfile.TemporaryDirectory(dir=ETC) as tmp:
            k, c = Path(tmp)/'key', Path(tmp)/'cert'
            run('openssl','req','-x509','-newkey','rsa:3072','-nodes','-sha256','-days','1095','-subj','/CN=Nexus 3D gateway status','-addext',f'subjectAltName=IP:{cloud}','-keyout',str(k),'-out',str(c))
            os.chmod(k,0o600); os.replace(k,key); os.replace(c,cert)
    originals = {path: path.read_bytes() if path.exists() else None for path in paths}
    for name in ('telemetry.py','sample.py','serve.py'):
        path = LIB / name
        originals[path] = path.read_bytes() if path.exists() else None
        paths[path] = (SOURCE/name).read_bytes()
    try:
        for path, contents in paths.items():
            put(path, contents, 0o644)
        run('systemctl','daemon-reload')
        run('systemctl','start',SAMPLE+'.service')
        run('systemctl','enable','--now',SAMPLE+'.timer',NAME+'.socket')
        run('systemctl','restart',NAME+'.service')
        for unit in (SAMPLE+'.timer', NAME+'.service', NAME+'.socket'):
            if run('systemctl','is-active',unit) != 'active':
                raise ValueError('inactive gateway status unit')
    except Exception:
        for unit in (NAME+'.service',NAME+'.socket',SAMPLE+'.timer'):
            if originals.get(UNITS/unit) is None:
                subprocess.run(['systemctl','stop',unit],check=False)
                if unit.endswith(('.socket','.timer')):
                    subprocess.run(['systemctl','disable',unit],check=False)
        for path, original in originals.items():
            if original is None: path.unlink(missing_ok=True)
            else: put(path, original, 0o644)
        run('systemctl','daemon-reload')
        if originals[UNITS/(NAME+'.service')] is not None: run('systemctl','restart',NAME+'.service')
        raise
    fp = hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
    print(json.dumps(dict(cloud=cloud, gateway=gateway, cloud_id=status['Self']['ID'], site_id=peers[0]['ID'],
                          port=PORT, pin=fp, mapping=data['mapping'])))


if __name__ == '__main__':
    main()
