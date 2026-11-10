"""Admit the two paired Tailscale node keys to the private printer relay."""
import argparse
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import time


class Pair:
    def __init__(self, config):
        self.config = config
        self.keys = {}
        self.refreshed = 0

    def refresh(self):
        response = subprocess.run(
            ['/usr/bin/tailscale', 'status', '--json'], check=True,
            capture_output=True, timeout=4
        )
        status = json.loads(response.stdout)
        cloud = status['Self']
        site = [p for p in status['Peer'].values() if p.get('ID') == self.config['site_id']]
        if status.get('BackendState') != 'Running' or cloud.get('ID') != self.config['cloud_id'] or len(site) != 1:
            raise ValueError('pair_unavailable')
        keys = {'site': site[0]['PublicKey'], 'cloud': cloud['PublicKey']}
        if len(set(keys.values())) != 2 or not all(re.fullmatch(r'nodekey:[0-9a-f]{64}', k) for k in keys.values()):
            raise ValueError('invalid_node_identity')
        self.keys, self.refreshed = keys, time.monotonic()

    def admit(self, node, source):
        address = str(ipaddress.ip_address(source))
        role = 'site' if address == self.config['site_source'] else 'cloud' if address in self.config['cloud_sources'] else None
        if role is None or not isinstance(node, str) or not re.fullmatch(r'nodekey:[0-9a-f]{64}', node):
            return False
        if time.monotonic() - self.refreshed > 15 or not self.keys:
            self.refresh()
        return compare_digest(self.keys[role], node)


class Admission(BaseHTTPRequestHandler):
    def do_POST(self):
        allow = False
        try:
            length = int(self.headers['Content-Length'])
            if self.path == '/admit' and self.client_address[0] == '127.0.0.1' and 0 < length <= 512:
                message = json.loads(self.rfile.read(length))
                allow = self.server.pair.admit(message['NodePublic'], message['Source'])
        except (KeyError, ValueError, TypeError, OSError, subprocess.SubprocessError):
            pass
        payload = json.dumps({'Allow': allow}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('port', type=int)
    args = parser.parse_args()
    with HTTPServer(('127.0.0.1', args.port), Admission) as http:
        http.pair = Pair(json.loads(args.config.read_bytes()))
        http.serve_forever()
