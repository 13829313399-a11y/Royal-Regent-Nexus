"""Build a site-specific Windows guard from the cloud installation and verified field receipts."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


SOURCE = Path(__file__).resolve().parent
RUNTIME = ('guard.ps1', 'windows-network.ps1', 'RRFleetStatus.cs', 'RRWiredProbe.cs',
           'RRLinkAddress.cs', 'RRTcpSession.cs')
INSTALLER = ('Install.cmd', 'Uninstall.cmd', 'install-windows.ps1', 'launch.ps1', '使用说明.txt')


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def windows_file(name):
    data = (SOURCE / name).read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
    return b'\xef\xbb\xbf' + data if name.endswith('.txt') else data


def build(cloud, field, lan, output):
    devices = sorted(field['devices'], key=lambda d: d['no'])
    if [d['no'] for d in devices] != list(range(1, 19)):
        raise ValueError('expected eighteen verified printers')
    pins = [d['pin'].lower() for d in devices]
    ips = [str(ipaddress.IPv4Address(d['ip'])) for d in devices]
    if len(set(ips)) != 18 or len(set(pins)) != 18 or any(not re.fullmatch('[0-9a-f]{64}', p) for p in pins):
        raise ValueError('invalid or duplicate printer identity')
    subnets = {ipaddress.IPv4Network(f'{ip}/24', strict=False) for ip in ips}
    if len(subnets) != 1:
        raise ValueError('expected a single verified printer LAN /24')
    lan_prefix = str(subnets.pop().network_address).rsplit('.', 1)[0]
    mapping = '\n'.join(f"{d['no']}|{ip}|{pin}" for d, ip, pin in zip(devices, ips, pins))
    if (hashlib.sha256(mapping.encode('ascii')).hexdigest() != cloud['mapping'] or
            field['site_id'] != cloud['site_id'] or field['vpn_cloud'] != cloud['cloud']):
        raise ValueError('cloud and field fleet do not match')
    links = [(r['machine_no'], r['mac'].upper().replace(':', '-')) for r in lan['field_links'] if r['resolved']]
    addresses = [(r['machine_no'], r['ip']) for r in lan['socket_snapshot']]
    macs = dict(links)
    if (len(links) != 18 or len(set(macs.values())) != 18 or set(macs) != set(range(1, 19)) or
            any(not re.fullmatch('(?:[0-9A-F]{2}-){5}[0-9A-F]{2}', m) for m in macs.values()) or
            sorted(addresses) != [(d['no'], ip) for d, ip in zip(devices, ips)]):
        raise ValueError('LAN address bindings do not match the verified fleet')
    allowed = ('cloud', 'gateway', 'cloud_id', 'site_id', 'port', 'pin', 'mapping')
    site = {key: cloud[key] for key in allowed}
    site.update(hostname='3D', public_cloud=field['cloud_public'],
                devices=[{'no': d['no'], 'ip': ip, 'mac': macs[d['no']]} for d, ip in zip(devices, ips)])
    payload = {'site.json': json.dumps(site, indent=2).encode('ascii')}
    payload.update((name, windows_file(name)) for name in RUNTIME)
    payload['windows-network.ps1'] = payload['windows-network.ps1'].replace(
        b'__PRINTER_LAN_PREFIX__', lan_prefix.encode('ascii'))
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}
    payload['manifest.json'] = json.dumps(manifest, indent=2, sort_keys=True).encode('ascii')
    payload.update((name, windows_file(name)) for name in INSTALLER)
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as f:
        temporary = Path(f.name)
    try:
        with ZipFile(temporary, 'w') as archive:
            for name, data in payload.items():
                archive.writestr(ZipInfo(name), data, compress_type=ZIP_DEFLATED)
        with ZipFile(temporary) as archive:
            if archive.testzip() or any(archive.read(name) != data for name, data in payload.items()):
                raise ValueError('archive verification failed')
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('cloud_install', 'field_config', 'lan_receipt', 'output'):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    build(load(args.cloud_install), load(args.field_config), load(args.lan_receipt), args.output)
