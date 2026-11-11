"""Install the dedicated, source-limited two-node Tailscale relay on a systemd host."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import tempfile


PORT = 41642
CALLBACK = 41643
TABLE = "rr_3d_relay_local"
PREFIX = "rr-three-d-relay"
LIB = Path("/usr/local/lib") / PREFIX
ETC = Path("/etc") / PREFIX
UNITS = Path("/etc/systemd/system")


def run(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, **kwargs)


def ipv4(value):
    return str(ipaddress.IPv4Address(value))


def required_address(value, label, addresses):
    if value not in addresses:
        raise ValueError(f"{label} is missing from the admission source list")


def inputs(args):
    public = ipv4(args.public)
    p = args.input.resolve(strict=True)
    pair = json.loads((p / "pair.json").read_bytes())
    site = ipv4(pair["site_source"])
    cloud = {ipv4(addr) for addr in pair["cloud_sources"]}
    peers = json.loads(run("tailscale", "status", "--json").stdout)
    site_peer = [v for v in peers["Peer"].values() if v["ID"] == pair["site_id"]]
    if peers["Self"]["ID"] != pair["cloud_id"] or len(site_peer) != 1:
        raise ValueError("live tailnet pairing mismatch")
    if site not in {ep.rsplit(":", 1)[0] for ep in (site_peer[0].get("Addrs") or [])}:
        netmap = json.loads(run("tailscale", "debug", "netmap").stdout)
        peer = next(v for v in netmap["Peers"] if v.get("StableID") == pair["site_id"])
        if site not in {ep.rsplit(":", 1)[0] for ep in peer.get("Endpoints", [])}:
            raise ValueError("advertised public endpoint no longer matches approved source")
    route = json.loads(run("ip", "-j", "-4", "route", "get", public).stdout)[0]
    local = ipv4(route["prefsrc"])
    required_address(local, "local ENI", cloud)
    required_address(public, "public IP", cloud)
    if site in cloud or cloud != {local, public, "127.0.0.1"}:
        raise ValueError("unexpected admission source scope")
    binary = p / "derper"
    cert = p / f"{public}.crt"
    key = p / f"{public}.key"
    if not re.fullmatch(r"[0-9a-f]{64}", args.binary_sha256) or hashlib.sha256(binary.read_bytes()).hexdigest() != args.binary_sha256:
        raise ValueError("DERP executable checksum mismatch")
    der = ssl.PEM_cert_to_DER_cert(cert.read_text())
    if hashlib.sha256(der).hexdigest() != args.cert_sha256:
        raise ValueError("TLS certificate pin mismatch")
    run("openssl", "x509", "-in", str(cert), "-noout", "-checkend", "604800")
    run("openssl", "verify", "-CAfile", str(cert), "-verify_ip", public, str(cert))
    cert_pub = run("openssl", "x509", "-in", str(cert), "-noout", "-pubkey").stdout
    key_pub = run("openssl", "pkey", "-in", str(key), "-pubout").stdout
    if cert_pub != key_pub or (key.stat().st_mode & 0o077):
        raise ValueError("TLS private key mode or public key mismatch")
    return p, public, local, site


def configuration(public, local, site):
    nft = f"""table ip {TABLE} {{
    chain output {{
        type nat hook output priority -105; policy accept;
        ip daddr {public} tcp dport {PORT} dnat to {local}:{PORT}
        ip daddr {public} udp dport {PORT} dnat to {local}:{PORT}
    }}
    chain local_source {{
        type nat hook postrouting priority 90; policy accept;
        oifname "lo" ct original ip daddr {public} ip saddr {local} ip daddr {local} udp dport {PORT} snat to {public}
    }}
    chain input {{
        type filter hook input priority -5; policy accept;
        iifname "lo" ip daddr {local} ip saddr {public} udp dport {PORT} accept
        ip daddr {local} ip saddr != {{ 127.0.0.1, {local}, {site} }} tcp dport {PORT} counter drop
        ip daddr {local} ip saddr != {{ 127.0.0.1, {local}, {site} }} udp dport {PORT} counter drop
    }}
}}
"""
    net_unit = f"""[Unit]
Description=RR 3D relay dedicated port filter and local EIP route
Wants=network-online.target
After=network-online.target nftables.service
Before={PREFIX}.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/nft -f {ETC}/network.nft
ExecStop=/usr/sbin/nft delete table ip {TABLE}
"""
    hardening = """DynamicUser=yes
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
UMask=0077
Restart=on-failure
RestartSec=3
IPAddressDeny=any
"""
    admission = f"""[Unit]
Description=RR 3D relay node admission
Wants=tailscaled.service
After=tailscaled.service

[Service]
{hardening}RestrictAddressFamilies=AF_UNIX AF_INET
IPAddressAllow=127.0.0.1/32
LoadCredential=pair.json:{ETC}/pair.json
ExecStart=/usr/bin/python3 -B {LIB}/admission.py ${{CREDENTIALS_DIRECTORY}}/pair.json {CALLBACK}
"""
    service = f"""[Unit]
Description=RR 3D paired-node encrypted fallback relay
Wants=network-online.target
Requires={PREFIX}-admission.service {PREFIX}-local-route.service
After=network-online.target {PREFIX}-admission.service {PREFIX}-local-route.service

[Service]
{hardening}RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
IPAddressAllow=127.0.0.1/32 {local}/32 {site}/32 {public}/32
StateDirectory={PREFIX}
StateDirectoryMode=0700
WorkingDirectory=/var/lib/{PREFIX}
LoadCredential={public}.crt:{ETC}/{public}.crt
LoadCredential={public}.key:{ETC}/{public}.key
ExecStart={LIB}/derper -a {local}:{PORT} -http-port=-1 -stun=true -stun-port={PORT} -hostname {public} -certmode=manual -certdir=${{CREDENTIALS_DIRECTORY}} -c /var/lib/{PREFIX}/derper.conf -home=blank -verify-client-url=http://127.0.0.1:{CALLBACK}/admit -verify-client-url-fail-open=false

[Install]
WantedBy=multi-user.target
"""
    return {"network.nft": nft, PREFIX + "-local-route.service": net_unit,
            PREFIX + "-admission.service": admission, PREFIX + ".service": service}


def install(args):
    if os.geteuid() != 0:
        raise ValueError("run on the intended relay host as root")
    p, public, local, site = inputs(args)
    admission = Path(__file__).with_name("relay-admission.py")
    files = configuration(public, local, site)
    if not admission.is_file():
        raise ValueError("paired admission source missing")
    with tempfile.TemporaryDirectory() as tempdir:
        for name, content in files.items():
            (Path(tempdir) / name).write_text(content)
        targets = [(p / "derper", LIB / "derper", 0o755), (admission, LIB / "admission.py", 0o644),
                   (p / "pair.json", ETC / "pair.json", 0o600),
                   (p / f"{public}.crt", ETC / f"{public}.crt", 0o644),
                   (p / f"{public}.key", ETC / f"{public}.key", 0o600)]
        for name in files:
            targets.append((Path(tempdir) / name, (UNITS if name.endswith(".service") else ETC) / name, 0o644))
        for src, dst, mode in targets:
            if dst.exists() and (dst.is_symlink() or dst.read_bytes() != src.read_bytes() or dst.stat().st_mode & 0o777 != mode):
                raise ValueError(f"existing file differs at {dst}")
        active = subprocess.run(["systemctl", "is-active", "--quiet", PREFIX + ".service"]).returncode == 0
        if active and all(dst.exists() for _, dst, _ in targets):
            print("matching relay already active")
            return
        live_table = subprocess.run(["nft", "list", "table", "ip", TABLE], capture_output=True)
        if live_table.returncode == 0:
            raise ValueError("named nft table already in use")
        for port in (PORT, CALLBACK):
            if run("ss", "-Hlnut", f"sport = :{port}").stdout.strip():
                raise ValueError(f"port {port} already in use")
        run("nft", "-c", "-f", str(Path(tempdir) / "network.nft"))
        if not args.apply:
            print("verified paired nodes, source, checksum, TLS pin, free ports, target paths and nft rules")
            return
        created = []
        try:
            LIB.mkdir(parents=True, mode=0o755, exist_ok=True)
            ETC.mkdir(parents=True, mode=0o700, exist_ok=True)
            for src, dst, mode in targets:
                if dst.exists():
                    continue
                with dst.open("xb") as out:
                    created.append(dst)
                    os.fchmod(out.fileno(), mode)
                    with src.open("rb") as inp:
                        shutil.copyfileobj(inp, out)
            run("systemctl", "daemon-reload")
            run("systemd-analyze", "verify", *[str(UNITS / k) for k in files if k.endswith(".service")])
            run("systemctl", "enable", "--now", PREFIX + ".service")
        except BaseException:
            subprocess.run(["systemctl", "disable", "--now", PREFIX + ".service"], capture_output=True)
            subprocess.run(["systemctl", "stop", PREFIX + "-admission.service", PREFIX + "-local-route.service"], capture_output=True)
            for dst in reversed(created):
                dst.unlink(missing_ok=True)
            run("systemctl", "daemon-reload")
            raise
    print("installed source-scoped relay, local route and admission service")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--public", required=True)
    parser.add_argument("--binary-sha256", required=True)
    parser.add_argument("--cert-sha256", required=True)
    parser.add_argument("--apply", action="store_true", help="install after validation")
    try:
        install(parser.parse_args())
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"command failed ({exc.returncode}): {exc.stderr.decode(errors='replace')[:850]}")
