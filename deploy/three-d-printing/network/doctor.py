"""Read-only route/TCP/certificate-pin/MQTT checks. Never publish printer commands."""

import argparse
import hashlib
import ipaddress
import json
import os
import re
import socket
import ssl
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from network_config import load_config

UTC = timezone.utc


def run_json(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=8, check=True)
    if len(result.stdout) > 4_000_000:
        raise ValueError("command_output_too_large")
    return json.loads(result.stdout)


def route_ok(config, printer, source=None):
    vpn = config["vpn"]
    rows = run_json(
        [
            "ip",
            "-j",
            "route",
            "get",
            printer["ip"],
            "from",
            source or vpn["connector_ip"],
        ]
    )
    return bool(
        rows
        and rows[0].get("dev") == vpn["interface"]
        and rows[0].get("type", "unicast") == "unicast"
    )


def tunnel_health(config):
    vpn = config["vpn"]
    try:
        if vpn["type"] == "wireguard":
            # Never use `wg show dump`: it includes the interface private key.
            result = subprocess.run(
                ["wg", "show", vpn["interface"], "latest-handshakes"],
                capture_output=True,
                text=True,
                timeout=8,
                check=True,
            )
            stamps = {
                parts[0]: int(parts[1])
                for line in result.stdout.splitlines()
                if len(parts := line.split()) == 2
            }
            age = time.time() - stamps.get(vpn["gateway_public_key"], 0)
            return "ok" if 0 <= age <= 180 else "failed"
        if vpn["type"] == "tailscale":
            data = run_json(["tailscale", "status", "--json"])
            peer = next(
                (
                    p
                    for p in data.get("Peer", {}).values()
                    if vpn["gateway_ip"] in p.get("TailscaleIPs", [])
                ),
                None,
            )
            return (
                "ok"
                if data.get("BackendState") == "Running" and peer and peer.get("Online")
                else "failed"
            )
        # Installed policy can survive a dead tunnel; require a live IKE + CHILD SA.
        # Never query XFRM state, which contains cryptographic keys.
        sas = subprocess.run(
            ["swanctl", "--list-sas", "--ike", "heyuan-3d", "--raw"],
            capture_output=True,
            text=True,
            timeout=8,
            check=True,
        )
        if not re.search(r"\bstate=ESTABLISHED\b", sas.stdout) or not re.search(
            r"\bstate=INSTALLED\b", sas.stdout
        ):
            return "failed"
        policies = run_json(["ip", "-j", "xfrm", "policy"])
        return (
            "ok"
            if any(
                p.get("dir") == "out" and str(p.get("if_id")) in {"330", "0x14a"}
                for p in policies
            )
            else "failed"
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return "unknown"


def read_secret(root, ref):
    root = Path(root).resolve()
    path = (root / (ref + ".json")).resolve()
    if path.parent != root or path.stat().st_size > 16384:
        raise ValueError("invalid_secret_file")
    if os.name != "nt" and path.stat().st_mode & 0o077:
        raise ValueError("secret_file_permissions")
    data = json.loads(path.read_text(encoding="utf-8"))
    if set(data) != {"serial", "access_code"} or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,64}", data["serial"]
    ):
        raise ValueError("invalid_secret_fields")
    if (
        not isinstance(data["access_code"], str)
        or not 1 <= len(data["access_code"]) <= 128
    ):
        raise ValueError("invalid_device_credential")
    return data


def mqtt_string(value):
    content = value.encode("utf-8")
    if len(content) > 65535:
        raise ValueError("mqtt_string_too_long")
    return struct.pack("!H", len(content)) + content


def packet(header, body):
    remaining, size = bytearray(), len(body)
    while True:
        digit, size = size % 128, size // 128
        remaining.append(digit | (128 if size else 0))
        if not size:
            return bytes([header]) + bytes(remaining) + body


def read_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        part = sock.recv(size - len(data))
        if not part:
            raise ValueError("mqtt_closed")
        data.extend(part)
    return bytes(data)


def mqtt_packet(sock):
    header = read_exact(sock, 1)[0]
    length = 0
    for index in range(4):
        digit = read_exact(sock, 1)[0]
        length += (digit & 127) * (128**index)
        if length > 65536:
            raise ValueError("mqtt_packet_too_large")
        if not digit & 128:
            return header, read_exact(sock, length)
    raise ValueError("mqtt_invalid_length")


def mqtt_check(sock, secret):
    # Clean, unique diagnostic client; no persistent session and no publish packet.
    client_id = "rr-doctor-" + os.urandom(8).hex()
    connect = mqtt_string("MQTT") + bytes([4, 0xC2]) + struct.pack("!H", 10)
    connect += (
        mqtt_string(client_id)
        + mqtt_string("bblp")
        + mqtt_string(secret["access_code"])
    )
    sock.sendall(packet(0x10, connect))
    if mqtt_packet(sock) != (0x20, b"\x00\x00"):
        raise ValueError("mqtt_auth_rejected")
    subscribe = (
        b"\x00\x01" + mqtt_string("device/" + secret["serial"] + "/report") + b"\x00"
    )
    sock.sendall(packet(0x82, subscribe))
    # A broker may send retained report packets before SUBACK. Bound their count/size.
    for _ in range(8):
        header, body = mqtt_packet(sock)
        if header == 0x90:
            if body != b"\x00\x01\x00":
                raise ValueError("mqtt_subscription_rejected")
            sock.sendall(b"\xe0\x00")
            return
        if header >> 4 != 3:
            raise ValueError("unexpected_mqtt_packet")
    raise ValueError("mqtt_suback_missing")


class DeadlineSocket:
    def __init__(self, sock, timeout):
        self.sock = sock
        self.deadline = time.monotonic() + timeout

    def _remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("probe_deadline")
        self.sock.settimeout(remaining)

    def recv(self, size):
        self._remaining()
        return self.sock.recv(size)

    def sendall(self, data):
        self._remaining()
        self.sock.sendall(data)


def probe_printer(config, printer, secret_root, timeout=3, authenticate=True):
    result = {
        "machine_no": printer["machine_no"],
        "route": "failed",
        "tcp": "skipped",
        "tls": "skipped",
        "mqtt": "skipped",
        "latency_ms": None,
    }
    try:
        if not route_ok(config, printer):
            return result
        result["route"], result["tcp"] = "ok", "failed"
        started = time.monotonic()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as raw:
            raw.settimeout(timeout)
            raw.bind((config["vpn"]["connector_ip"], 0))
            raw.connect((printer["ip"], 8883))
            result["latency_ms"] = round((time.monotonic() - started) * 1000, 3)
            result["tcp"], result["tls"] = "ok", "failed"
            pin = printer["cert_sha256"].lower()
            if not re.fullmatch(r"[a-f0-9]{64}", pin):
                return result
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.check_hostname = False
            # Self-signed device certificates use an out-of-band verified DER SHA256 pin.
            # Credentials are never loaded/sent until that identity check succeeds.
            context.verify_mode = ssl.CERT_NONE
            with context.wrap_socket(raw, server_hostname=None) as sock:
                if (
                    hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest()
                    != pin
                ):
                    return result
                result["tls"] = "ok"
                if not authenticate:
                    return result
                result["mqtt"] = "failed"
                secret = read_secret(secret_root, printer["credential_ref"])
                mqtt_check(DeadlineSocket(sock, timeout), secret)
                result["mqtt"] = "ok"
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        pass  # Deliberately emit stage codes only, never raw exceptions/device payloads.
    return result


def exposure_audit(document, config):
    """Scoped DNAT/redirect inventory, not proof of all perimeter ACLs."""
    if not isinstance(document, dict) or not isinstance(document.get("nftables"), list):
        return "unknown"
    network = ipaddress.ip_network(config["lan"]["cidr"])
    status = "ok"

    def walk(value):
        nonlocal status
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "dnat":
                    try:
                        address = ipaddress.ip_network(item["addr"], strict=False)
                        if address.version == 4 and address.overlaps(network):
                            status = "unsafe"
                    except (KeyError, ValueError, TypeError):
                        if status != "unsafe":
                            status = "unknown"  # sets/maps/dynamic destinations need manual expansion
                elif key in {"redirect", "tproxy"} and status != "unsafe":
                    status = "unknown"
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(document)
    return status


def negative_probe(config, source_ip, timeout):
    source = ipaddress.ip_address(source_ip)
    if (
        source.version != 4
        or not source.is_private
        and source not in ipaddress.ip_network("100.64.0.0/10")
    ):
        raise ValueError("private_negative_test_source_required")
    if source_ip == config["vpn"]["connector_ip"]:
        raise ValueError("negative_test_needs_other_identity")
    results = []
    for printer in config["printers"]:
        state = "inconclusive"
        try:
            if route_ok(config, printer, source_ip):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(timeout)
                    sock.bind(
                        (source_ip, 0)
                    )  # Binding must succeed before rejection can count.
                    try:
                        sock.connect((printer["ip"], 8883))
                        state = "unexpected_access"
                    except (TimeoutError, ConnectionRefusedError):
                        state = "not_reachable"
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        results.append({"machine_no": printer["machine_no"], "result": state})
    return {
        "mode": "negative",
        "results": results,
        "requires_positive_control": True,
        "acl_proven": False,
    }  # Compare with contemporaneous positive probe + firewall counters.


def report(config, secret_root, timeout=3, nft_documents=(), authenticate=False):
    observed_at = datetime.now(UTC).isoformat()
    with ThreadPoolExecutor(max_workers=4) as executor:
        rows = list(
            executor.map(
                lambda p: probe_printer(config, p, secret_root, timeout, authenticate),
                config["printers"],
            )
        )
    statuses = [exposure_audit(doc, config) for doc in nft_documents]
    exposure = (
        "unsafe"
        if "unsafe" in statuses
        else "ok"
        if len(statuses) >= 2 and set(statuses) == {"ok"}
        else "unknown"
    )
    return {
        "factory_id": config["factory_id"],
        "site_id": config["site_id"],
        "gateway_key": config["gateway_key"],
        "vpn_type": config["vpn"]["type"],
        "observed_at": observed_at,
        "probe_level": "mqtt" if authenticate else "network",
        "tunnel": tunnel_health(config),
        "exposure": exposure,
        "printers": rows,
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def upload(data, url, token_file):
    parsed = urllib.parse.urlsplit(url)
    if (
        (parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1", "localhost"}
        ))
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("https_report_endpoint_required")
    if parsed.path != "/api/three-d-printing/network/health":
        raise ValueError("invalid_report_endpoint")
    token = Path(token_file).read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", token):
        raise ValueError("invalid_report_token")
    request = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "X-Three-D-Network-Token": token},
    )
    with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
        if response.status != 200:
            raise ValueError("report_rejected")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--mode", choices=["validate", "probe", "negative", "audit"], default="validate"
    )
    parser.add_argument("--secrets-dir")
    parser.add_argument(
        "--mqtt-auth",
        action="store_true",
        help="Explicit one-shot MQTT login/subscription acceptance; no publishing",
    )
    parser.add_argument("--timeout", type=float, default=3)
    parser.add_argument("--nft-json", action="append", default=[])
    parser.add_argument("--source-ip")
    parser.add_argument("--report-url")
    parser.add_argument("--token-file")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if not 0.1 <= args.timeout <= 5:
            raise ValueError("invalid_timeout")
        docs = [
            json.loads(Path(path).read_text(encoding="utf-8")) for path in args.nft_json
        ]
        if args.mode == "validate":
            data = {"status": "valid_topology_not_connectivity", "printer_count": 11}
        elif args.mode == "audit":
            data = {
                "status": "not_global_exposure_proof",
                "results": [exposure_audit(doc, config) for doc in docs],
            }
        elif args.mode == "negative":
            data = negative_probe(config, args.source_ip, args.timeout)
        else:
            if args.mqtt_auth and not args.secrets_dir:
                raise ValueError("secrets_directory_required")
            data = report(config, args.secrets_dir, args.timeout, docs, args.mqtt_auth)
            if args.report_url:
                upload(data, args.report_url, args.token_file)
        print(json.dumps(data, ensure_ascii=False))
        if args.mode == "probe":
            return (
                0
                if data["tunnel"] == "ok"
                and data["exposure"] != "unsafe"
                and all(
                    p["mqtt" if args.mqtt_auth else "tls"] == "ok"
                    for p in data["printers"]
                )
                else 1
            )
        if args.mode == "audit":
            return 0 if docs and set(data["results"]) == {"ok"} else 1
        if args.mode == "negative":
            return (
                1 if any(p["result"] != "not_reachable" for p in data["results"]) else 0
            )
        return 0
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.SubprocessError,
        urllib.error.URLError,
    ):
        print('{"status":"error","code":"configuration_or_probe_failed"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
