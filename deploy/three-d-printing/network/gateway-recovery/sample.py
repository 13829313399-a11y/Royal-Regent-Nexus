"""Publish a short-lived read-only status document. The network server has no Docker access."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def checked(args, data=None):
    return subprocess.run(args, input=data, capture_output=True, check=True, timeout=12).stdout


def established_peers():
    peers = set()
    for pid in checked(['lsns', '-nr', '-t', 'net', '-o', 'PID']).decode().split():
        lines = checked(['nsenter', '-t', pid, '-n', 'ss', '-Htn', 'state', 'established', '( dport = :8883 )']).decode().splitlines()
        for line in lines:
            fields = line.split()
            if len(fields) != 4:
                raise ValueError('unexpected_socket_table')
            peers.add(fields[-1].rsplit(':', 1)[0].strip('[]').removeprefix('::ffff:'))
    return peers


def collect(api, connector, gateway):
    raw = Path(__file__).with_name('telemetry.py').read_bytes()
    result = json.loads(checked(['docker', 'exec', '-i', api, 'python', '-'], raw))
    container = json.loads(checked(['docker', 'inspect', connector]))[0]
    if not container['State']['Running'] or container['HostConfig']['NetworkMode'] != 'host':
        result['collector_ok'] = False
    net = json.loads(checked(['tailscale', 'status', '--json']))
    routes = [p for p in net.get('Peer', {}).values() if gateway in (p.get('TailscaleIPs') or [])]
    result['routes_ok'] = bool(net.get('BackendState') == 'Running' and len(routes) == 1 and
                               all(r['ip'] + '/32' in (routes[0].get('PrimaryRoutes') or []) for r in result['printers']))
    # A live connection in any cloud namespace vetoes targeted Windows socket release.
    # If a namespace or its listing is unreadable, the old snapshot expires.
    peers = established_peers()
    for row in result['printers']:
        row['tcp_open'] = row.pop('ip') in peers
    return result


def publish(file, data):
    with tempfile.NamedTemporaryFile('w', dir=file.parent, delete=False) as out:
        temp = Path(out.name)
        try:
            json.dump(data, out, separators=(',', ':'))
            out.flush()
            os.fchmod(out.fileno(), 0o644)
            os.fsync(out.fileno())
            os.replace(temp, file)
        finally:
            temp.unlink(missing_ok=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('output', type=Path)
    p.add_argument('api')
    p.add_argument('connector')
    p.add_argument('gateway')
    opts = p.parse_args()
    publish(opts.output, collect(opts.api, opts.connector, opts.gateway))
