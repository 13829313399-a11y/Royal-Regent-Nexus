"""Serve only a recent telemetry summary to the paired gateway on a VPN-bound socket."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import socket
import ssl
import time


class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/v1/fleet' or self.client_address[0] != self.server.gateway:
            self.send_error(404)
            return
        try:
            data = self.server.status_path.read_bytes()
            if len(data) > 8192 or not 0 <= time.time() - json.loads(data)['timestamp'] <= 60:
                raise ValueError('expired')
        except (OSError, ValueError, KeyError, TypeError):
            self.send_error(503)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        receipt = self.headers.get('X-RR-Guard', '')
        if re.fullmatch(r'[34]\|[0-9]{1,10}\|(?:[0-9]|1[0-8])\|(?:none|attempted|released_awaiting_telemetry|service_running_awaiting_telemetry|telemetry_recovered|tuple_not_released_-?[0-9]{1,6})', receipt):
            print('field_guard', receipt, flush=True)

    def log_message(self, fmt, *args):
        # Only the fixed route and response status are useful for installation checks.
        if fmt.startswith('"%s"') and self.command == 'GET' and self.path == '/v1/fleet':
            print('field_fleet_read', args[1], flush=True)


class StatusServer(HTTPServer):
    def get_request(self):
        stream, address = self.socket.accept()
        try:
            if address[0] != self.gateway:
                raise OSError('unpaired_source')
            stream.settimeout(4)
            return self.tls.wrap_socket(stream, server_side=True), address
        except Exception:
            stream.close()
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('gateway'); parser.add_argument('status', type=Path)
    args = parser.parse_args()
    if os.environ.get('LISTEN_PID') != str(os.getpid()) or os.environ.get('LISTEN_FDS') != '1':
        raise SystemExit('a VPN-bound systemd socket is required')
    with StatusServer(('127.0.0.1', 0), StatusHandler, bind_and_activate=False) as server:
        server.socket.close()
        server.socket = socket.socket(fileno=3)
        server.server_name, server.server_port = server.socket.getsockname()
        server.gateway, server.status_path = args.gateway, args.status
        server.tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.tls.minimum_version = ssl.TLSVersion.TLSv1_2
        credentials = Path(os.environ['CREDENTIALS_DIRECTORY'])
        server.tls.load_cert_chain(credentials / 'server.crt', credentials / 'server.key')
        server.serve_forever()
